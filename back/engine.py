import asyncio
import websockets
import json
import soundcard as sc
import soundfile as sf
import io
import base64
import warnings
import traceback
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
from mss import mss
from PIL import Image

try:
    from back.config import HUME_API_KEY, TOUS_LES_GROUPES
except ImportError:
    from config import HUME_API_KEY, TOUS_LES_GROUPES

warnings.filterwarnings("ignore", message="data discontinuity in recording")

app = FastAPI()

# Variables globales pour le HUD
hud_coords = {"x": 0, "y": 0, "w": 0, "h": 0}
sct = mss()

def get_hud_image():
    """Capture l'écran à l'intérieur de la Bounding Box du HUD Electron"""
    if hud_coords["w"] <= 0 or hud_coords["h"] <= 0:
        return None
    
    try:
        screenshot = sct.grab({
            "top": int(hud_coords["y"]), 
            "left": int(hud_coords["x"]), 
            "width": int(hud_coords["w"]), 
            "height": int(hud_coords["h"])
        })
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        img.thumbnail((250, 250))
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=70)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"Erreur de capture d'écran: {e}")
        return None


async def connexion_hume(electron_ws: WebSocket):
    uri = f"wss://api.hume.ai/v0/stream/models?apikey={HUME_API_KEY}"
    print("⏳ Connexion au serveur Hume AI...")

    micro_loopback = None
    recorder = None
    hume_ws = None

    try:
        hp_par_defaut = sc.default_speaker().name
        micro_loopback = sc.get_microphone(id=str(hp_par_defaut), include_loopback=True)
        print(f"[AUDIO] Interception audio activée sur : {hp_par_defaut}")
    except Exception as e:
        print(f"[ERREUR] Erreur de configuration audio : {e}")
        traceback.print_exc()
        return

    try:
        hume_ws = await websockets.connect(uri)
        print("[OK] LIGNE DIRECTE OUVERTE AVEC HUME !")

        recorder = micro_loopback.recorder(samplerate=44100)
        recorder.__enter__()

        while True:
            # Vérifier si Electron est toujours connecté
            if electron_ws.client_state.name == "DISCONNECTED":
                break

            # --- CAPTURE DES FLUX ---
            donnees_audio = recorder.record(numframes=44100)
            buffer_audio = io.BytesIO()
            sf.write(buffer_audio, donnees_audio, 44100, format='WAV', subtype='PCM_16')
            audio_base64 = base64.b64encode(buffer_audio.getvalue()).decode('utf-8')

            image_actuelle_base64 = get_hud_image()

            # --- ENVOI AUX MODÈLES ---
            await hume_ws.send(json.dumps({
                "models": {"prosody": {}},
                "data": audio_base64
            }))

            if image_actuelle_base64:
                await hume_ws.send(json.dumps({
                    "models": {"face": {}},
                    "data": image_actuelle_base64
                }))

            emotion_visage_actuelle = None
            score_visage = 0
            emotion_voix_actuelle = None
            score_voix = 0

            # --- RÉCUPÉRATION DES PRÉDICTIONS ---
            nb_reponses_attendues = 2 if image_actuelle_base64 else 1
            reponses_recues = 0

            while reponses_recues < nb_reponses_attendues:
                try:
                    reponse = await asyncio.wait_for(hume_ws.recv(), timeout=5.0)
                    reponses_recues += 1
                    donnees = json.loads(reponse)

                    if 'face' in donnees and 'predictions' in donnees['face']:
                        try:
                            emotions = donnees['face']['predictions'][0]['emotions']
                            dominante = max(emotions, key=lambda x: x['score'])
                            emotion_visage_actuelle = dominante['name']
                            score_visage = dominante['score'] * 100
                            print(f"[VISAGE] VISAGE : {emotion_visage_actuelle} ({score_visage:.0f}%)")
                        except (KeyError, IndexError, TypeError) as e:
                            print(f"[WARN] Format réponse face inattendu : {e}")

                    if 'prosody' in donnees and 'predictions' in donnees['prosody']:
                        try:
                            emotions = donnees['prosody']['predictions'][0]['emotions']
                            dominante = max(emotions, key=lambda x: x['score'])
                            emotion_voix_actuelle = dominante['name']
                            score_voix = dominante['score'] * 100
                            print(f"[VOIX] VOIX   : {emotion_voix_actuelle} ({score_voix:.0f}%)")
                        except (KeyError, IndexError, TypeError) as e:
                            print(f"[WARN] Format réponse prosody inattendu : {e}")

                except asyncio.TimeoutError:
                    print("[TIMEOUT] Timeout en attendant une réponse de Hume")
                    break

            # --- RATE LIMITING ---
            await asyncio.sleep(0.5)

            # ==========================================================
            # MOTEUR DE DISSONANCE (FUSION MULTIMODALE)
            # ==========================================================

            if emotion_visage_actuelle and emotion_voix_actuelle:
                SEUIL_MIN_VISAGE = 30
                SEUIL_MIN_VOIX = 15

                if score_visage > SEUIL_MIN_VISAGE and score_voix > SEUIL_MIN_VOIX:
                    def trouver_quadrant(emotion):
                        for nom_quadrant, liste_emotions in TOUS_LES_GROUPES.items():
                            if emotion in liste_emotions:
                                return nom_quadrant
                        return "Inconnu"

                    quadrant_visage = trouver_quadrant(emotion_visage_actuelle)
                    quadrant_voix = trouver_quadrant(emotion_voix_actuelle)

                    if quadrant_visage != "Inconnu" and quadrant_voix != "Inconnu":
                        dissonance_value = 0
                        alert_level = "NONE"

                        if quadrant_visage != quadrant_voix:
                            indice_certitude = (score_visage + score_voix) / 2
                            dissonance_value = indice_certitude

                            print("\n" + "***" + "="*45)
                            if indice_certitude > 60:
                                alert_level = "SEVERE"
                                print(f"[ALERTE] ALERTE : DISSONANCE SÉVÈRE (Certitude: {indice_certitude:.1f}%)")
                            elif indice_certitude > 40:
                                alert_level = "MODERATE"
                                print(f"[WARN] ALERTE : DISSONANCE MODÉRÉE (Certitude: {indice_certitude:.1f}%)")
                            else:
                                alert_level = "VIGILANCE"
                                print(f"[INFO] INFO : VIGILANCE REQUISE (Certitude: {indice_certitude:.1f}%)")

                            print(f"[VISAGE] Visage : {emotion_visage_actuelle} -> {quadrant_visage}")
                            print(f"[VOIX] Voix   : {emotion_voix_actuelle} -> {quadrant_voix}")
                            print("="*45 + "***" + "\n")

                        # Envoi à Electron
                        await electron_ws.send_json({
                            "type": "dissonance",
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "value": dissonance_value,
                            "alert_level": alert_level,
                            "face": f"{emotion_visage_actuelle} ({score_visage:.0f}%)",
                            "voice": f"{emotion_voix_actuelle} ({score_voix:.0f}%)",
                            "quadrant_face": quadrant_visage
                        })

    except asyncio.CancelledError:
        print("[STOP] Tâche Hume annulée proprement.")
        raise
    except Exception as e:
        print(f"[WARN] Erreur Hume : {e}")
        traceback.print_exc()
    finally:
        if recorder is not None:
            try:
                recorder.__exit__(None, None, None)
                print("[AUDIO] Recorder audio fermé.")
            except Exception as e:
                print(f"[WARN] Erreur fermeture recorder : {e}")
        if hume_ws is not None:
            try:
                await hume_ws.close()
                print("[WS] Connexion Hume fermée.")
            except Exception as e:
                print(f"[WARN] Erreur fermeture Hume WS : {e}")

def vibrer_bracelet(intensite, type_vibration):
    """
    Fonction factice pour simuler l'envoi d'une commande de vibration au bracelet.
    """
    print(f"[VIBRATION] TEST BRACELET - Type: {type_vibration} | Intensité: {intensite}/100")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[WS] Client Electron (HUD) connecté au WebSocket.")
    
    # Démarrer la boucle Hume en tâche de fond pour cette session
    task = asyncio.create_task(connexion_hume(websocket))
    
    try:
        while True:
            data = await websocket.receive_json()
            if "type" in data and data["type"] == "test_vibration":
                vibrer_bracelet(data.get("intensity", 50), data.get("test_type", "inconnu"))
            elif "x" in data and "y" in data and "w" in data and "h" in data:
                global hud_coords
                hud_coords = {
                    "x": data["x"],
                    "y": data["y"],
                    "w": data["w"],
                    "h": data["h"]
                }
    except WebSocketDisconnect:
        print("[WS] Client Electron déconnecté.")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    print("[SERVEUR] Serveur FastAPI démarré sur http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")