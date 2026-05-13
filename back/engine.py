import asyncio
import websockets
import json
import soundcard as sc
import soundfile as sf
import io
import base64
import warnings
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
    
    try:
        hp_par_defaut = sc.default_speaker().name
        micro_loopback = sc.get_microphone(id=str(hp_par_defaut), include_loopback=True)
        print(f"🎙️ Interception audio activée sur : {hp_par_defaut}")
    except Exception as e:
        print(f"❌ Erreur de configuration audio : {e}")
        return
    
    try:
        async with websockets.connect(uri) as hume_ws:
            print("✅ LIGNE DIRECTE OUVERTE AVEC HUME !")
            
            with micro_loopback.recorder(samplerate=44100) as recorder:
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
                    for _ in range(2): 
                        reponse = await hume_ws.recv()
                        donnees = json.loads(reponse)
                        
                        if 'face' in donnees and 'predictions' in donnees['face']:
                            try:
                                emotions = donnees['face']['predictions'][0]['emotions']
                                dominante = max(emotions, key=lambda x: x['score'])
                                emotion_visage_actuelle = dominante['name']
                                score_visage = dominante['score'] * 100
                            except: pass 
                                
                        if 'prosody' in donnees and 'predictions' in donnees['prosody']:
                            try:
                                emotions = donnees['prosody']['predictions'][0]['emotions']
                                dominante = max(emotions, key=lambda x: x['score'])
                                emotion_voix_actuelle = dominante['name']
                                score_voix = dominante['score'] * 100
                            except: pass 

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
                                is_alert = False
                                
                                if quadrant_visage != quadrant_voix:
                                    indice_certitude = (score_visage + score_voix) / 2
                                    dissonance_value = indice_certitude
                                    is_alert = indice_certitude > 60
                                
                                # Envoi à Electron
                                await electron_ws.send_json({
                                    "type": "dissonance",
                                    "value": dissonance_value,
                                    "isAlert": is_alert,
                                    "face": f"{emotion_visage_actuelle} ({score_visage:.0f}%)",
                                    "voice": f"{emotion_voix_actuelle} ({score_voix:.0f}%)"
                                })
                                
    except Exception as e:
        print(f"⚠️ Erreur Hume : {e}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔌 Client Electron (HUD) connecté au WebSocket.")
    
    # Démarrer la boucle Hume en tâche de fond pour cette session
    task = asyncio.create_task(connexion_hume(websocket))
    
    try:
        while True:
            data = await websocket.receive_json()
            if "x" in data and "y" in data and "w" in data and "h" in data:
                global hud_coords
                hud_coords = {
                    "x": data["x"],
                    "y": data["y"],
                    "w": data["w"],
                    "h": data["h"]
                }
    except WebSocketDisconnect:
        print("🔌 Client Electron déconnecté.")
        task.cancel()

if __name__ == "__main__":
    print("🚀 Serveur FastAPI démarré sur http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")