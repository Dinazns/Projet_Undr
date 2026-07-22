"""Configuration centrale : constantes du pipeline et variables d'environnement."""
import os
from typing import Dict, List, Tuple
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration FastAPI
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# Configuration BLE
MAC_MONTRE = os.getenv("MAC_MONTRE", "7B:0B:A5:16:62:0C")
FEE2_UUID = "0000fee2-0000-1000-8000-00805f9b34fb"

# Coordonnées (valence, arousal) de chaque émotion dans le plan de Russell.
# Valence : -1 (négatif) à +1 (positif). Arousal : -1 (calme) à +1 (actif).
EMOTION_COORDINATES: Dict[str, Tuple[float, float]] = {
    # Q1 (Actif/Positif) - Valence +, Arousal +
    "happy": (0.8, 0.7),
    "joy": (0.9, 0.8),
    "surprise": (0.2, 0.9),
    "excited": (0.7, 0.9),
    "enthusiastic": (0.8, 0.8),

    # Q2 (Calme/Positif) - Valence +, Arousal -
    "calm": (0.5, -0.8),
    "content": (0.6, -0.6),
    "satisfied": (0.7, -0.5),
    "relaxed": (0.6, -0.8),

    # Q3 (Passif/Négatif) - Valence -, Arousal -
    "sad": (-0.8, -0.7),
    "bored": (-0.5, -0.8),
    "tired": (-0.3, -0.9),
    "disappointed": (-0.7, -0.6),
    "confused": (-0.2, -0.3),

    # Q4 (Actif/Négatif) - Valence -, Arousal +
    "angry": (-0.8, 0.8),
    "fear": (-0.7, 0.9),
    "disgust": (-0.9, 0.5),
    "anxious": (-0.6, 0.7),
    "frustrated": (-0.7, 0.6),

    # Q5 (Neutre) - origine du plan (0, 0), ni positif ni négatif
    "neutral": (0.0, 0.0),
}

# Émotions regroupées par quadrant. neutral est à l'origine (0,0), donc isolé
# dans sa propre catégorie pour ne pas être compté comme une valence positive.
EMOTION_GROUPS: Dict[str, List[str]] = {
    "Q1 (Actif/Positif)": ["happy", "joy", "surprise", "excited", "enthusiastic"],
    "Q2 (Calme/Positif)": ["calm", "content", "satisfied", "relaxed"],
    "Q3 (Passif/Négatif)": ["sad", "bored", "tired", "disappointed", "confused"],
    "Q4 (Actif/Négatif)": ["angry", "fear", "disgust", "anxious", "frustrated"],
    "Q5 (Neutre)": ["neutral"],
}

# Confiance minimale pour exploiter une émotion. Le filtrage principal est fait
# dans EmotionService ; ici, un garde-fou plus souple.
SEUIL_MIN_VISAGE = 28

# Réglages de la détection faciale.
FACE_MIN_DETECTION_CONFIDENCE = 0.6  # MediaPipe : filtre les faux visages
FACE_MIN_SIZE_PX = 64                 # en dessous, la prédiction n'est pas fiable
# Fenêtre de lissage temporel. La boucle tourne à ~3 s (cadence audio), donc
# 3 itérations ≈ 9 s. Au-delà, la détection devient molle et en retard.
FACE_SMOOTH_WINDOW = 3
FACE_TARGET_SIZE = 96                 # taille du crop avant FER

# Porte de stabilité du label facial. FER fluctue d'une frame à l'autre et
# surestime "happy". On n'accepte un label que si sa confiance dépasse
# FACE_MIN_CONFIDENCE et devance le 2e label de FACE_MIN_MARGIN, sinon None.
FACE_MIN_CONFIDENCE = 35.0
FACE_MIN_MARGIN = 8.0

# Moteur de classification faciale : "fer" (CNN FER-2013) ou "emotiefflib"
# (EfficientNet AffectNet, modèle multi-tâches qui sort valence/arousal en
# continu, comme la voix). EmotiEffLib est plus précis sur happy/sad et évite
# l'approximation du barycentre. Bascule via la variable d'environnement.
FACE_ENGINE = os.getenv("FACE_ENGINE", "fer").lower()
EMOTIEFFLIB_MODEL = os.getenv("EMOTIEFFLIB_MODEL", "enet_b0_8_va_mtl")
# La valence/arousal d'EmotiEffLib (AffectNet) est calibrée mais resserrée
# (rarement au-delà de ±0.5), là où le barycentre FER atteignait les bords.
# Ce gain la ramène sur une plage comparable pour que les seuils de dissonance
# restent valides. À baisser si trop d'alertes, à monter si trop peu.
EMOTIEFFLIB_VA_GAIN = float(os.getenv("EMOTIEFFLIB_VA_GAIN", "1.8"))

# Le modèle vocal est une régression (valence/arousal), sans probabilité native.
# On approxime la confiance par la distance au centre (0,0), normalisée par cette
# magnitude "très confiant". À recalibrer selon les logs.
VOICE_MAX_EXPECTED_MAGNITUDE = 0.5
# Aligné sur le plancher de _confidence_weight (28) pour éviter une zone morte.
SEUIL_MIN_VOIX = 28

# Seuil de dissonance : distance dans le plan valence-arousal (max ≈ 2.83).
SEUIL_DISSONANCE_DISTANCE = 0.8

# Correction cross-modale : quand la voix contredit franchement le label facial,
# on neutralise ce dernier (FER confond happy/sad dans les deux sens).
VOICE_NEG_THRESHOLD = -0.15
VOICE_POS_THRESHOLD = 0.15
# Le veto ne s'applique qu'aux labels faibles : un sourire franc contredit par
# une voix négative est un vrai masquage, pas une erreur à corriger.
FACE_VETO_MAX_CONFIDENCE = 45.0

# La vibration exige une dissonance persistante (PERSISTENCE_MIN fenêtres sur
# PERSISTENCE_WINDOW) et un délai minimum entre deux vibrations. Le dashboard,
# lui, reçoit tous les événements.
PERSISTENCE_WINDOW = 3
PERSISTENCE_MIN = 2
VIBRATION_COOLDOWN_SECONDS = 15

# Configuration audio
SAMPLERATE = 16000
# Périphérique loopback (None = HP par défaut). Certains casques BT/USB ne
# renvoient rien en loopback ; viser alors la carte interne (ex. Realtek Digital Output).
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", None)

# Configuration BLE - Commandes Moyoung
NOTIF_CALL = 0
NOTIF_CALL_OFF_HOOK = 0xFF