"""
API FastAPI principale - Point d'entrée de l'application.
Gère la connexion WebSocket avec le frontend, la capture audio/vidéo et la détection de dissonance.
"""
import asyncio
import functools
import logging
import os
import sys
import time
import warnings
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import soundcard as sc

# Forcer le CPU (pas de GPU requis)
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Le loopback soundcard émet un warning bénin à chaque capture, et httpx trace
# chaque requête HuggingFace : on les masque pour garder des logs lisibles.
warnings.filterwarnings("ignore", message="data discontinuity in recording")
logging.getLogger("httpx").setLevel(logging.WARNING)

# Imports des modules locaux
from config import (
    API_HOST, API_PORT, DEBUG, SAMPLERATE, AUDIO_DEVICE,
    ANALYSIS_WINDOW_SECONDS, FACE_SAMPLE_INTERVAL, FACE_MIN_SAMPLES,
)
from services import ble_service, emotion_service, AnalysisSession
from utils import ScreenCapture
import numpy as np


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gère le cycle de vie de l'application (démarrage/arrêt)"""
    # Code exécuté au démarrage
    logger.info("Démarrage de l'application...")
    
    # Initialiser la capture d'écran
    app.state.screen_capture = ScreenCapture()
    
    yield
    
    # Code exécuté à l'arrêt
    logger.info("Arrêt de l'application...")
    await ble_service.disconnect()
    for executor in (_face_executor, _voice_executor, _audio_executor):
        executor.shutdown(wait=False, cancel_futures=True)


# Créer l'application FastAPI
app = FastAPI(
    title="API Détection Dissonance Émotionnelle",
    description="API multimodale pour détecter la dissonance émotionnelle",
    version="2.0.0",
    lifespan=lifespan
)


# Trois exécuteurs à un seul thread, un par ressource bloquante.
#
# Les moteurs d'inférence embarqués ne sont pas tous garantis thread-safe :
# l'interpréteur TFLite de MediaPipe ne l'est pas, et les objets de capture
# WASAPI de soundcard supportent mal le changement de thread. asyncio.to_thread
# puise dans un pool partagé et fait donc migrer chaque appel d'un thread à
# l'autre. Confiner chaque modèle à un thread unique supprime ce risque, évite
# le coût de va-et-vient entre threads (environ huit fois par fenêtre côté
# visage) et garantit qu'aucune inférence ne peut s'exécuter en parallèle d'une
# autre sur le même modèle.
_face_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="undr-face")
_voice_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="undr-voice")
_audio_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="undr-audio")

# Demande de réinitialisation du contexte, posée par le client entre deux
# séquences ou au début d'une séance.
_reset_requested = asyncio.Event()


async def _sample_face_window(screen_capture: ScreenCapture, duration: float) -> list:
    """
    Échantillonne le visage PENDANT la fenêtre audio, à cadence régulière.

    C'est le correctif du décalage entre canaux. L'ancienne boucle capturait une
    seule image APRÈS les 3 s d'enregistrement : on comparait donc un instantané
    pris à t+3 s à une moyenne prosodique couvrant [t, t+3 s]. Les deux mesures
    ne portaient pas sur le même moment, et une expression apparue en début de
    fenêtre était systématiquement manquée.

    La capture d'écran (mss) reste sur la boucle d'événements, mss n'étant pas
    thread-safe. Seule l'inférence part dans un thread, ce qui laisse
    l'enregistrement audio progresser en parallèle.
    """
    loop = asyncio.get_running_loop()
    samples = []
    deadline = time.monotonic() + duration
    while True:
        if deadline - time.monotonic() <= 0:
            break
        tick = time.monotonic()
        # Image transmise telle quelle (ndarray BGR) : aucun encodage JPEG ni
        # base64 intermédiaire, tout se passe dans le même processus.
        frame = screen_capture.capture_hud_array()
        if frame is not None:
            sample = await loop.run_in_executor(
                _face_executor, emotion_service.analyze_face_frame, frame
            )
            if sample:
                samples.append(sample)
        elapsed = time.monotonic() - tick
        pause = min(
            max(0.0, FACE_SAMPLE_INTERVAL - elapsed),
            max(0.0, deadline - time.monotonic()),
        )
        if pause > 0:
            await asyncio.sleep(pause)
    return samples


async def process_stream(websocket: WebSocket, screen_capture: ScreenCapture):
    """
    Boucle d'analyse. Une itération = une fenêtre temporelle unique, décrite
    simultanément par le canal vocal (enregistrement continu) et par le canal
    visuel (plusieurs images échantillonnées pendant ce même enregistrement).

    Cette fonction ne fait qu'acquérir les deux canaux et transmettre les
    résultats : toute la logique de décision est dans AnalysisSession, partagée
    avec le banc d'évaluation hors ligne (tools/evaluate_corpus.py).
    """
    try:
        # Périphérique loopback : celui configuré, sinon le HP par défaut.
        if AUDIO_DEVICE:
            device_id = AUDIO_DEVICE
            logger.info(f"Interception audio sur peripherique configure : {device_id}")
        else:
            device_id = str(sc.default_speaker().name)
            logger.info(f"Interception audio sur haut-parleur par defaut : {device_id}")
        micro_loopback = sc.get_microphone(id=device_id, include_loopback=True)

        session = AnalysisSession(emotion_service)
        _reset_requested.clear()

        loop = asyncio.get_running_loop()
        n_frames = int(SAMPLERATE * ANALYSIS_WINDOW_SECONDS)
        expected_frames = int(ANALYSIS_WINDOW_SECONDS / FACE_SAMPLE_INTERVAL)
        logger.info(
            "Fenêtre d'analyse : %.1f s | échantillonnage visage toutes les %.2f s "
            "(%d images attendues, minimum %d)",
            ANALYSIS_WINDOW_SECONDS, FACE_SAMPLE_INTERVAL,
            expected_frames, FACE_MIN_SAMPLES,
        )
        if expected_frames < FACE_MIN_SAMPLES:
            logger.warning(
                "Configuration incohérente : au mieux %d image(s) par fenêtre alors "
                "que FACE_MIN_SAMPLES vaut %d. Aucune fenêtre ne sera exploitable. "
                "Baissez FACE_SAMPLE_INTERVAL ou FACE_MIN_SAMPLES.",
                expected_frames, FACE_MIN_SAMPLES,
            )

        with micro_loopback.recorder(samplerate=SAMPLERATE) as recorder:
            while True:
                if websocket.client_state.name == "DISCONNECTED":
                    logger.info("Client déconnecté, arrêt du flux")
                    break

                if _reset_requested.is_set():
                    _reset_requested.clear()
                    session.reset(reason="demande du client")

                window_started = time.monotonic()

                # Les deux canaux sont acquis sur le MÊME intervalle temporel.
                audio_data, face_samples = await asyncio.gather(
                    loop.run_in_executor(
                        _audio_executor,
                        functools.partial(recorder.record, numframes=n_frames),
                    ),
                    _sample_face_window(screen_capture, ANALYSIS_WINDOW_SECONDS),
                )

                # Toute la décision, dans le thread dédié à l'inférence vocale :
                # c'est la seule inférence lourde de cette étape (le visage a
                # déjà été inféré pendant l'acquisition).
                outcome = await loop.run_in_executor(
                    _voice_executor,
                    session.process_window,
                    face_samples, audio_data, SAMPLERATE,
                )

                window_seconds = time.monotonic() - window_started

                if outcome.is_dissonant:
                    logger.info(
                        "Dissonance détectée ! Niveau: %s | Confiance: %.1f%% | "
                        "Distance: %.2f | fenêtre=%.2f s | %d image(s) visage | "
                        "dispersion=%.2f",
                        outcome.alert_level, outcome.confidence, outcome.emotion_distance,
                        window_seconds, outcome.n_face_samples, outcome.face_dispersion,
                    )
                    logger.info(
                        "  Visage: %s (%.0f%%) | Voix: %s (%.0f%%)",
                        outcome.face_emotion, outcome.face_score,
                        outcome.voice_emotion, outcome.voice_score,
                    )

                    if outcome.should_vibrate:
                        await ble_service.vibrate()

                    await websocket.send_json({
                        "type": "dissonance",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "value": float(outcome.confidence),
                        "alert_level": outcome.alert_level,
                        "face": (
                            f"{outcome.face_emotion} ({float(outcome.face_score):.0f}%)"
                            if outcome.face_emotion else None
                        ),
                        "voice": (
                            f"{outcome.voice_emotion} ({float(outcome.voice_score):.0f}%)"
                            if outcome.voice_emotion else None
                        ),
                        # Quadrants déduits du POINT mesuré, pas du label : les deux
                        # sont des sorties distinctes du même réseau et peuvent se
                        # contredire.
                        "quadrant_face": emotion_service.quadrant_from_coords(outcome.face_coords),
                        "quadrant_voice": emotion_service.quadrant_from_coords(outcome.voice_coords),
                        "face_coords": list(outcome.face_coords) if outcome.face_coords else None,
                        "voice_coords": list(outcome.voice_coords) if outcome.voice_coords else None,
                        "emotion_distance": float(outcome.emotion_distance),
                        # Métadonnées de fenêtre : sur quel support temporel la
                        # mesure a réellement été faite. Traçabilité indispensable
                        # pour reporter une latence honnête.
                        "window_seconds": round(window_seconds, 2),
                        "face_samples": int(outcome.n_face_samples),
                        "face_dispersion": (
                            round(float(outcome.face_dispersion), 3)
                            if outcome.face_dispersion is not None else None
                        ),
                    })
                else:
                    logger.debug(
                        "Fenêtre non retenue (%s) | visage=%s voix=%s",
                        outcome.skipped or "sous le seuil",
                        outcome.face_emotion, outcome.voice_emotion,
                    )

                # Télémétrie envoyée à CHAQUE fenêtre, dissonance ou non.
                # Sans elle, l'interface reste muette tant qu'aucune alerte ne se
                # déclenche : pendant une démonstration, un système qui fonctionne
                # correctement mais ne détecte rien est indiscernable d'un système
                # en panne. Ces événements ne sont pas enregistrés côté tableau de
                # bord, ils ne servent qu'à rendre l'analyse visible en direct.
                await websocket.send_json({
                    "type": "telemetry",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "face": outcome.face_emotion,
                    "face_score": round(float(outcome.face_score), 1),
                    "voice": outcome.voice_emotion,
                    "voice_score": round(float(outcome.voice_score), 1),
                    "distance": round(float(outcome.emotion_distance), 3),
                    "alert_level": outcome.alert_level,
                    "face_samples": int(outcome.n_face_samples),
                    "face_dispersion": (
                        round(float(outcome.face_dispersion), 3)
                        if outcome.face_dispersion is not None else None
                    ),
                    "skipped": outcome.skipped,
                    "window_seconds": round(window_seconds, 2),
                })

                # Aucune pause supplémentaire : la fenêtre d'analyse cadence déjà
                # la boucle (ANALYSIS_WINDOW_SECONDS + temps d'inférence).

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Erreur dans le flux: {e}", exc_info=True)



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint WebSocket pour la communication avec le frontend."""
    await websocket.accept()
    logger.info("Client connecté au WebSocket")

    screen_capture = app.state.screen_capture
    stream_task = None

    try:
        # Démarrer la tâche de traitement du flux
        stream_task = asyncio.create_task(process_stream(websocket, screen_capture))

        while True:
            data = await websocket.receive_json()
            logger.debug(f"Reçu du client: {data}")

            # Mettre à jour les coordonnées du HUD
            if all(key in data for key in ["x", "y", "w", "h"]):
                screen_capture.set_hud_coords(
                    data["x"], data["y"], data["w"], data["h"]
                )
                # En debug : envoyé ~2x/seconde par le frontend.
                logger.debug("Coordonnées HUD mises à jour")

            # Test de vibration
            if data.get("type") == "test_vibration":
                await ble_service.vibrate()

            # Réinitialisation du contexte : à envoyer entre deux séquences de
            # test, ou au début d'une séance. Sans cela, le premier visage d'une
            # nouvelle scène est comparé à la voix de la scène précédente.
            if data.get("type") == "reset_context":
                _reset_requested.set()
                logger.info("Réinitialisation du contexte demandée par le client")

    except WebSocketDisconnect:
        logger.info("Client déconnecté du WebSocket")
    except Exception as e:
        logger.error(f"Erreur WebSocket: {e}", exc_info=True)
    finally:
        screen_capture.clear_hud_coords()
        if stream_task:
            stream_task.cancel()
            # Une inférence déjà partie dans un exécuteur n'est pas annulable :
            # au pire, on attend la fin de la fenêtre en cours. Le délai borne
            # cette attente pour ne pas retenir la fermeture de la connexion.
            try:
                await asyncio.wait_for(stream_task, ANALYSIS_WINDOW_SECONDS + 2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.error("Erreur à l'arrêt du flux : %s", e)


@app.get("/health")
async def health_check():
    """Endpoint de vérification de l'état de l'API."""
    return {
        "status": "healthy",
        "ble_connected": ble_service.is_connected,
        # Latence du dernier write GATT, en ms. À utiliser pour reporter la
        # latence BLE réelle plutôt que la durée du motif de vibration.
        "last_ble_write_ms": ble_service.last_write_latency_ms,
        "analysis_window_seconds": ANALYSIS_WINDOW_SECONDS,
        "face_sample_interval": FACE_SAMPLE_INTERVAL,
    }


@app.get("/calibration")
async def calibration():
    """
    Distributions observées des deux canaux, pour calibrer l'harmonisation
    d'échelle (EMOTIEFFLIB_VA_GAIN) sur des données réelles plutôt qu'au jugé.
    """
    return emotion_service.get_calibration_stats()


@app.post("/ble/connect")
async def ble_connect():
    """Endpoint pour connecter la montre BLE."""
    try:
        await ble_service.connect(sync_time=False)
        return {
            "status": "connected",
            "ble_connected": ble_service.is_connected,
        }
    except Exception as e:
        logger.error(f"Erreur connexion BLE: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "ble_connected": ble_service.is_connected,
        }


@app.post("/ble/disconnect")
async def ble_disconnect():
    """Endpoint pour déconnecter la montre BLE."""
    try:
        await ble_service.disconnect()
        return {
            "status": "disconnected",
            "ble_connected": ble_service.is_connected,
        }
    except Exception as e:
        logger.error(f"Erreur déconnexion BLE: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "ble_connected": ble_service.is_connected,
        }


@app.get("/ble/status")
async def ble_status():
    """Endpoint pour obtenir l'état de la connexion BLE."""
    return {
        "ble_connected": ble_service.is_connected,
    }


# ---------------------------------------------------------------------------
# Audio : choix du périphérique de capture loopback
# ---------------------------------------------------------------------------

def _list_loopback_devices() -> list:
    """Retourne la liste des micros disposant d'un mode loopback."""
    devices = []
    try:
        for m in sc.all_microphones(include_loopback=True):
            devices.append({
                "id": str(m.id),
                "name": str(m.name),
                "is_loopback": bool(getattr(m, "isloopback", False)),
            })
    except Exception as e:
        logger.error(f"Erreur listing micros: {e}", exc_info=True)
    return devices


def _measure_energy(device_id: str, duration: float = 1.0) -> float:
    """Mesure l'énergie RMS (0-1) captée sur un device loopback."""
    try:
        mic = sc.get_microphone(id=device_id, include_loopback=True)
        # Le _Recorder de soundcard n'initialise ses buffers que dans __enter__ :
        # appeler .record() sans passer par un "with" plante sur _pending_chunk.
        with mic.recorder(samplerate=SAMPLERATE) as recorder:
            data = recorder.record(numframes=int(SAMPLERATE * duration))
        if data is None or data.size == 0:
            return 0.0
        # Moyenne RMS sur tous les canaux
        rms = float(np.sqrt(np.mean(np.square(data.astype(np.float32)))))
        return min(rms, 1.0)
    except Exception as e:
        logger.error(f"Erreur mesure energie [{device_id}]: {e}", exc_info=True)
        return -1.0


@app.get("/audio/devices")
async def audio_devices():
    """Liste tous les micros loopback disponibles."""
    return {
        "current": AUDIO_DEVICE,
        "default_speaker": str(sc.default_speaker().name) if sc.default_speaker() else None,
        "devices": _list_loopback_devices(),
    }


@app.get("/audio/test")
async def audio_test(device_id: str = None, duration: float = 1.0):
    """
    Mesure l'énergie audio captée sur un device (loopback) donné.
    Si device_id est omis, utilise le device configuré ou le HP par défaut.
    """
    if not device_id:
        device_id = AUDIO_DEVICE or str(sc.default_speaker().name)
    energy = _measure_energy(device_id, duration)
    return {
        "device_id": device_id,
        "energy": energy,
        "has_signal": energy > 0.001,
    }


@app.post("/audio/device")
async def audio_set_device(payload: dict):
    """
    Persiste le choix du périphérique loopback dans le .env local.
    payload = {"device_id": "..."}  (None/"" = revenir au HP par défaut)
    """
    global AUDIO_DEVICE
    device_id = payload.get("device_id") or None

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        # Retirer l'ancienne clé AUDIO_DEVICE
        lines = [ln for ln in lines if not ln.startswith("AUDIO_DEVICE=")]

        if device_id:
            lines.append(f'AUDIO_DEVICE="{device_id}"\n')

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        AUDIO_DEVICE = device_id  # reflet en mémoire pour le flux courant
        logger.info(
            "Périphérique audio persisté : %s. Le flux en cours continue sur "
            "l'ancien périphérique : relancer la session pour appliquer.",
            device_id,
        )
        return {"status": "ok", "device_id": AUDIO_DEVICE}
    except Exception as e:
        logger.error(f"Erreur écriture .env audio: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=DEBUG)