"""
API FastAPI principale - Point d'entrée de l'application.
Gère la connexion WebSocket avec le frontend, la capture audio/vidéo et la détection de dissonance.
"""
import asyncio
import logging
import os
import sys
import time
import warnings
from collections import deque
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, Any

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
    API_HOST, API_PORT, DEBUG, SEUIL_MIN_VISAGE, SEUIL_MIN_VOIX, SAMPLERATE,
    AUDIO_DEVICE, PERSISTENCE_WINDOW, PERSISTENCE_MIN, VIBRATION_COOLDOWN_SECONDS,
)
from services import ble_service, emotion_service
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


# Créer l'application FastAPI
app = FastAPI(
    title="API Détection Dissonance Émotionnelle",
    description="API multimodale pour détecter la dissonance émotionnelle",
    version="2.0.0",
    lifespan=lifespan
)


async def process_stream(websocket: WebSocket, screen_capture: ScreenCapture):
    """
    Traite le flux audio et vidéo et envoie les résultats au frontend.
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

        # Persistance : la vibration exige une dissonance confirmée sur plusieurs
        # fenêtres. Cooldown : délai minimum entre deux vibrations.
        recent_dissonant = deque(maxlen=PERSISTENCE_WINDOW)
        last_vibration_ts = 0.0

        with micro_loopback.recorder(samplerate=SAMPLERATE) as recorder:
            while True:
                # Vérifier la connexion WebSocket
                if websocket.client_state.name == "DISCONNECTED":
                    logger.info("Client déconnecté, arrêt du flux")
                    break

                # Fenêtre audio de 3 s : assez de contexte pour une estimation
                # vocale stable.
                AUDIO_WINDOW_SECONDS = 3
                audio_data = await asyncio.to_thread(
                    recorder.record, numframes=int(SAMPLERATE * AUDIO_WINDOW_SECONDS)
                )
                image_base64 = screen_capture.capture_hud()

                face_emotion, face_score, face_coords = None, 0.0, None
                if image_base64:
                    face_emotion, face_score, face_coords = await asyncio.to_thread(
                        emotion_service.detect_face_emotion, image_base64
                    )

                voice_emotion, voice_score, voice_coords = await asyncio.to_thread(
                    emotion_service.detect_audio_emotion, audio_data, SAMPLERATE
                )

                # Correction cross-modale : neutralise un label facial faible
                # contredit par la voix. Un sourire franc + voix négative
                # (masquage) est conservé.
                face_emotion = emotion_service.reconcile_face_emotion(
                    face_emotion, voice_coords, face_score
                )

                is_dissonant, confidence, alert_level, emotion_distance = False, 0.0, "NONE", 0.0
                if face_emotion and face_score > SEUIL_MIN_VISAGE and voice_emotion and voice_score > SEUIL_MIN_VOIX:
                    # voice_coords / face_coords : points continus (valence, arousal)
                    # des deux canaux.
                    is_dissonant, confidence, alert_level, emotion_distance = emotion_service.detect_dissonance(
                        face_emotion, face_score, voice_emotion, voice_score, voice_coords, face_coords
                    )

                recent_dissonant.append(1 if is_dissonant else 0)

                if is_dissonant:
                        logger.info(
                            f"Dissonance détectée ! Niveau: {alert_level}, Confiance: {confidence:.1f}%, Distance: {emotion_distance:.2f}"
                        )
                        logger.info(
                            f"Visage: {face_emotion} ({face_score:.0f}% | Voix: {voice_emotion} ({voice_score:.0f}%"
                        )

                        # Vibration seulement sur MODERATE/SEVERE, si la dissonance
                        # est confirmée sur plusieurs fenêtres, et hors cooldown.
                        # VIGILANCE reste visible dans les logs et le dashboard.
                        confirmed = sum(recent_dissonant) >= PERSISTENCE_MIN
                        now = time.monotonic()
                        if (
                            alert_level in ("MODERATE", "SEVERE")
                            and confirmed
                            and now - last_vibration_ts >= VIBRATION_COOLDOWN_SECONDS
                        ):
                            await ble_service.vibrate()
                            last_vibration_ts = now
                        elif alert_level in ("MODERATE", "SEVERE") and not confirmed:
                            logger.info(
                                "Vibration différée : dissonance non confirmée (%d/%d fenêtres)",
                                sum(recent_dissonant), PERSISTENCE_MIN,
                            )

                        # Coordonnées continues envoyées au dashboard (mapping de Russell).
                        await websocket.send_json({
                            "type": "dissonance",
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "value": float(confidence),
                            "alert_level": alert_level,
                            "face": f"{face_emotion} ({float(face_score):.0f}%)" if face_emotion else None,
                            "voice": f"{voice_emotion} ({float(voice_score):.0f}%)" if voice_emotion else None,
                            "quadrant_face": emotion_service.get_emotion_quadrant(face_emotion) if face_emotion else None,
                            "quadrant_voice": emotion_service.get_emotion_quadrant(voice_emotion) if voice_emotion else None,
                            "face_coords": list(face_coords) if face_coords else None,
                            "voice_coords": list(voice_coords) if voice_coords else None,
                            "emotion_distance": float(emotion_distance),
                        })
                else:
                    if face_emotion:
                        logger.debug(f"Visage: {face_emotion} ({face_score:.0f}%)")
                    if voice_emotion:
                        logger.debug(f"Voix: {voice_emotion} ({voice_score:.0f}%)")

                # Limiter la fréquence de traitement
                await asyncio.sleep(0.5)

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

    except WebSocketDisconnect:
        logger.info("Client déconnecté du WebSocket")
    except Exception as e:
        logger.error(f"Erreur WebSocket: {e}", exc_info=True)
    finally:
        screen_capture.clear_hud_coords()
        if stream_task:
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass


@app.get("/health")
async def health_check():
    """Endpoint de vérification de l'état de l'API."""
    return {
        "status": "healthy",
        "ble_connected": ble_service.is_connected,
    }


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
        logger.info(f"Périphérique audio persisté : {device_id}")
        return {"status": "ok", "device_id": AUDIO_DEVICE}
    except Exception as e:
        logger.error(f"Erreur écriture .env audio: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=DEBUG)