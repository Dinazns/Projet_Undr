# engine.py
import asyncio
import websockets
import json
import soundcard as sc
import soundfile as sf
import io
import base64
import warnings
from back.config import HUME_API_KEY, TOUS_LES_GROUPES

warnings.filterwarnings("ignore", message="data discontinuity in recording")

async def connexion_hume(obtenir_image_callback):
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
        async with websockets.connect(uri) as websocket:
            print("✅ LIGNE DIRECTE OUVERTE (VISAGE ET VOIX) !")
            
            with micro_loopback.recorder(samplerate=44100) as recorder:
                while True:
                    # Audio
                    donnees_audio = recorder.record(numframes=44100)
                    buffer_audio = io.BytesIO()
                    sf.write(buffer_audio, donnees_audio, 44100, format='WAV', subtype='PCM_16')
                    audio_base64 = base64.b64encode(buffer_audio.getvalue()).decode('utf-8')
                    
                    # On appelle le Front pour récupérer la dernière image
                    image_actuelle_base64 = obtenir_image_callback()
                    
                    # Envoi Voix
                    await websocket.send(json.dumps({
                        "models": {"prosody": {}},
                        "data": audio_base64
                    }))
                    
                    # Envoi Visage
                    if image_actuelle_base64:
                        await websocket.send(json.dumps({
                            "models": {"face": {}},
                            "data": image_actuelle_base64
                        }))
                    
                    emotion_visage_actuelle = None
                    score_visage = 0
                    emotion_voix_actuelle = None
                    score_voix = 0
                    
                    for _ in range(2): 
                        reponse = await websocket.recv()
                        donnees = json.loads(reponse)
                        
                        # Extraction Visage
                        if 'face' in donnees and 'predictions' in donnees['face']:
                            try:
                                emotions = donnees['face']['predictions'][0]['emotions']
                                dominante = max(emotions, key=lambda x: x['score'])
                                emotion_visage_actuelle = dominante['name']
                                score_visage = dominante['score'] * 100
                                print(f"👁️ VISAGE : {emotion_visage_actuelle} ({score_visage:.0f}%)")
                            except: pass 
                                
                        # Extraction Voix
                        if 'prosody' in donnees and 'predictions' in donnees['prosody']:
                            try:
                                emotions = donnees['prosody']['predictions'][0]['emotions']
                                dominante = max(emotions, key=lambda x: x['score'])
                                emotion_voix_actuelle = dominante['name']
                                score_voix = dominante['score'] * 100
                                print(f"🗣️ VOIX   : {emotion_voix_actuelle} ({score_voix:.0f}%)")
                            except: pass 

                    # Moteur de Dissonance
                    if emotion_visage_actuelle and emotion_voix_actuelle:
                        if score_visage > 30 and score_voix > 15:
                            def trouver_quadrant(emotion):
                                for nom_quadrant, liste_emotions in TOUS_LES_GROUPES.items():
                                    if emotion in liste_emotions:
                                        return nom_quadrant
                                return "Inconnu"
                                
                            quadrant_visage = trouver_quadrant(emotion_visage_actuelle)
                            quadrant_voix = trouver_quadrant(emotion_voix_actuelle)
                            
                            if quadrant_visage != "Inconnu" and quadrant_voix != "Inconnu":
                                if quadrant_visage != quadrant_voix:
                                    print("\n" + "⚠️"*25)
                                    print(f"🚨 ALERTE DISSONANCE SÉVÈRE 🚨")
                                    print(f"🎭 Visage : {emotion_visage_actuelle} -> {quadrant_visage}")
                                    print(f"🗣️ Voix   : {emotion_voix_actuelle} -> {quadrant_voix}")
                                    print("⚠️"*25 + "\n")
                                    
    except Exception as e:
        print(f"⚠️ Erreur de connexion : {e}")

def lancer_cerveau(obtenir_image_callback):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(connexion_hume(obtenir_image_callback))