# Backend - Système de Détection de Dissonance Émotionnelle

Version 2.0 - Professionnel et maintenable

## Fonctionnalités
- Détection multimodale d'émotions (visage + voix)
- Détection de dissonance émotionnelle (modèle Russell)
- Intégration avec la montre Blackview R50 via BLE (vibration sur alerte)
- API FastAPI avec WebSocket pour la communication avec le frontend
- Optimisé pour fonctionner exclusivement sur CPU

## Structure du Projet
```
back/
├── api/
│   ├── __init__.py
│   └── main.py              # Point d'entrée FastAPI, WebSocket endpoint
├── config/
│   ├── __init__.py
│   └── settings.py          # Configuration centrale (variables d'environnement, constantes)
├── services/
│   ├── __init__.py
│   ├── ble_service.py       # Service de communication BLE avec la montre
│   └── emotion_service.py   # Service de détection d'émotions multimodale
├── utils/
│   ├── __init__.py
│   └── screen_capture.py    # Utilitaire de capture d'écran pour le HUD
├── requirements.txt         # Dépendances
├── README_BACKEND.md        # Ce fichier
└── engine_old.py            # Ancien fichier (pour référence)
```

## Installation

1. Créez un environnement virtuel (recommandé) :
   ```bash
   py -3.10.9 -m venv venv
   # Sur Windows
   venv\Scripts\activate
   ```

2. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

3. (Optionnel) Créez un fichier `.env` pour personnaliser la configuration :
   ```env
   API_HOST=127.0.0.1
   API_PORT=8000
   DEBUG=True
   MAC_MONTRE=7B:0B:A5:16:62:0C
   ```

## Utilisation

### Démarrage du serveur
```bash
python -m api.main
```

OU si vous préférez utiliser uvicorn directement :
```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

### Endpoints
- `GET /health` - Vérification de l'état de l'API
- `WebSocket /ws` - Communication avec le frontend (HUD)

## Services
### `BLEService` (Singleton)
Gère la connexion, l'envoi de notifications et les vibrations avec la montre Blackview R50.
- `connect()`: Se connecte à la montre et synchronise l'heure
- `vibrate()`: Fait vibrer la montre en simulant un appel entrant
- `disconnect()`: Déconnecte proprement la montre

### `EmotionService` (Singleton)
Gère la détection d'émotions et la détection de dissonance.
- `detect_face_emotion(image_base64)`: Détecte l'émotion faciale
- `detect_audio_emotion(audio_data, sample_rate)`: Détecte l'émotion vocale
- `detect_dissonance(...)`: Détecte la dissonance entre visage et voix
- `get_emotion_quadrant(emotion)`: Récupère le quadrant Russell d'une émotion

## Technologies Utilisées
- **FastAPI**: Framework API web moderne et rapide
- **FER**: Détection d'émotions faciales (léger pour CPU)
- **Bleak**: Communication BLE
- **MSS**: Capture d'écran rapide
- **NumPy/Pillow/OpenCV**: Traitement d'images/audio
- **Logging**: Système de logging professionnel

## Modèle Russell (Quadrants Émotionnels)
1. **Q1 (Actif/Positif)**: happy, joy, surprise, excited, enthusiastic
2. **Q2 (Calme/Positif)**: calm, neutral, content, satisfied, relaxed
3. **Q3 (Passif/Négatif)**: sad, bored, tired, disappointed, confused
4. **Q4 (Actif/Négatif)**: angry, fear, disgust, anxious, frustrated
