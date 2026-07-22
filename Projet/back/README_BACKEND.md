# Backend — Détection de dissonance émotionnelle

Backend Python (FastAPI) qui analyse en temps réel les expressions faciales et
la voix pour détecter une dissonance émotionnelle, et déclenche une vibration
sur une montre connectée. Tout tourne en local, sur CPU.

## Principe

Le système capture deux canaux et les projette dans le plan de Russell
(valence / arousal) :

- **Visage** : MediaPipe localise le visage dans la zone du HUD, FER classe
  l'émotion. La distribution complète est projetée en un point continu
  (barycentre), pas seulement le label dominant.
- **Voix** : le flux audio est intercepté en loopback (16 kHz) et analysé par le
  modèle audeering `wav2vec2-large-robust-12-ft-emotion-msp-dim`, qui renvoie
  directement un point (valence, arousal).

La dissonance est mesurée par la distance euclidienne entre les deux points.
Une logique floue gradue l'alerte en trois niveaux (VIGILANCE / MODERATE /
SEVERE). La vibration n'est envoyée que sur MODERATE/SEVERE, si la dissonance
persiste sur plusieurs fenêtres, et hors période de cooldown — pour éviter les
fausses alertes et la fatigue d'alarme.

## Structure

```
back/
├── api/
│   └── main.py              # FastAPI, endpoint WebSocket, boucle d'analyse
├── config/
│   └── settings.py          # Constantes du pipeline, coordonnées de Russell
├── services/
│   ├── ble_service.py       # Communication BLE avec la montre (protocole Moyoung)
│   └── emotion_service.py   # Détection faciale + vocale, calcul de dissonance
├── utils/
│   └── screen_capture.py    # Capture de la zone du HUD
├── models/
│   └── face_detector.task   # Modèle MediaPipe
├── download_model.py        # Téléchargement du modèle MediaPipe
└── requirements.txt
```

## Installation

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Un fichier `.env` optionnel permet de personnaliser la configuration :

```env
API_HOST=127.0.0.1
API_PORT=8000
MAC_MONTRE=7B:0B:A5:16:62:0C
AUDIO_DEVICE=            # périphérique loopback (vide = HP par défaut)
FACE_ENGINE=fer         # "fer" ou "emotiefflib"
```

### Moteur de classification faciale

Deux moteurs sont disponibles via `FACE_ENGINE` :

- `fer` : CNN entraîné sur FER-2013. Léger, mais confond parfois happy et sad.
- `emotiefflib` : EfficientNet entraîné sur AffectNet (backend ONNX). Plus
  robuste sur happy/sad et renvoie directement valence/arousal, exactement
  comme le canal vocal.

## Lancement

```bash
python -m api.main
```

Le premier démarrage télécharge le modèle vocal (~1 Go) depuis Hugging Face.

## Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| WS | `/ws` | Flux temps réel avec le frontend (coordonnées HUD, événements de dissonance) |
| GET | `/health` | État de l'API et de la connexion BLE |
| POST | `/ble/connect` · `/ble/disconnect` | Connexion / déconnexion de la montre |
| GET | `/ble/status` | État de la connexion BLE |
| GET | `/audio/devices` | Liste des périphériques loopback |
| GET | `/audio/test` | Mesure du niveau sonore capté sur un périphérique |
| POST | `/audio/device` | Choix du périphérique loopback (persisté dans `.env`) |

## Plan de Russell

Chaque émotion a des coordonnées (valence, arousal) réparties en quadrants :

- **Q1 — Actif/Positif** : happy, joy, surprise, excited, enthusiastic
- **Q2 — Calme/Positif** : calm, content, satisfied, relaxed
- **Q3 — Passif/Négatif** : sad, bored, tired, disappointed, confused
- **Q4 — Actif/Négatif** : angry, fear, disgust, anxious, frustrated
- **Q5 — Neutre** : neutral (origine du plan)

## Technologies

FastAPI · MediaPipe · FER · PyTorch / Transformers (wav2vec2) · librosa ·
soundcard · mss · bleak · OpenCV · NumPy · Pillow
