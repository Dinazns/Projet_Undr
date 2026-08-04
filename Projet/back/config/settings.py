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

# Réglages de la détection faciale.
FACE_MIN_DETECTION_CONFIDENCE = float(os.getenv("FACE_MIN_DETECTION_CONFIDENCE", "0.6"))
FACE_MIN_SIZE_PX = int(os.getenv("FACE_MIN_SIZE_PX", "64"))

# Côté le plus long de l'image capturée, en pixels. La capture n'est réduite que
# si elle dépasse cette taille. Monter cette valeur augmente la finesse du crop
# de visage (donc la qualité de la classification) au prix du temps d'inférence.
CAPTURE_MAX_SIZE = int(os.getenv("CAPTURE_MAX_SIZE", "448"))
# ---------------------------------------------------------------------------
# Alignement temporel des deux canaux
# ---------------------------------------------------------------------------
# Fenêtre d'analyse commune au visage et à la voix. Les deux canaux décrivent
# désormais le MÊME intervalle [t, t+ANALYSIS_WINDOW_SECONDS] : le visage est
# échantillonné PENDANT l'enregistrement audio, et non une seule fois après.
ANALYSIS_WINDOW_SECONDS = max(1.0, float(os.getenv("ANALYSIS_WINDOW_SECONDS", "3.0")))

# Cadence d'échantillonnage du visage à l'intérieur de la fenêtre.
# 0.35 s -> environ 8 images par fenêtre de 3 s sur un CPU courant.
FACE_SAMPLE_INTERVAL = max(0.05, float(os.getenv("FACE_SAMPLE_INTERVAL", "0.35")))

# Nombre minimum d'images exploitables pour qu'une fenêtre soit fusionnée.
# En dessous, le visage a été trop souvent absent ou trop petit : la fenêtre
# est ignorée plutôt que résumée par une ou deux images non représentatives.
FACE_MIN_SAMPLES = max(1, int(os.getenv("FACE_MIN_SAMPLES", "3")))

# Dispersion maximale du point facial dans la fenêtre (distance moyenne à la
# médiane, dans le plan de Russell). Au-delà, le visage a trop varié pour
# qu'un point unique le résume : la fenêtre n'est pas fusionnée.
FACE_MAX_DISPERSION = float(os.getenv("FACE_MAX_DISPERSION", "0.45"))

# Lissage INTER-fenêtres. 1 = désactivé. L'agrégation intra-fenêtre remplace
# l'ancien lissage sur 3 itérations qui, à ~3,8 s par tour, étalait le signal
# sur environ 11 secondes réelles.
FACE_SMOOTH_WINDOW = int(os.getenv("FACE_SMOOTH_WINDOW", "1"))
VOICE_SMOOTH_WINDOW = int(os.getenv("VOICE_SMOOTH_WINDOW", "1"))

# --- Ruptures de contexte --------------------------------------------------
# Purge de la mémoire d'un canal après N fenêtres consécutives sans signal
# exploitable. Corrige le cas : une séquence se termine (silence), une autre
# commence, et le nouveau visage est comparé à la voix de la séquence
# précédente encore présente dans l'historique.
# Une seule fenêtre sans signal ne suffit pas : dans un entretien, le patient
# se tait toutes les quelques secondes et sort régulièrement du cadre. Traiter
# chaque pause comme un changement de scène rendait la vibration presque
# inatteignable, puisqu'elle exige une dissonance confirmée sur plusieurs
# fenêtres consécutives. Trois fenêtres ≈ neuf secondes sans rien : là, il
# s'agit bien d'une rupture.
SILENCE_WINDOWS_BEFORE_RESET = int(os.getenv("SILENCE_WINDOWS_BEFORE_RESET", "3"))
NO_FACE_WINDOWS_BEFORE_RESET = int(os.getenv("NO_FACE_WINDOWS_BEFORE_RESET", "3"))

# Fenêtres valides ignorées après une purge, le temps que les deux canaux
# décrivent à nouveau la même scène.
WARMUP_WINDOWS_AFTER_RESET = int(os.getenv("WARMUP_WINDOWS_AFTER_RESET", "1"))

# Porte de stabilité du LABEL facial (affichage et quadrants uniquement : le
# calcul de dissonance utilise le point continu). Un label n'est retenu que si
# sa probabilité dépasse FACE_MIN_CONFIDENCE et devance la deuxième classe de
# FACE_MIN_MARGIN. Ces valeurs ont été réglées sur les 7 classes de FER : à
# revérifier sur les 8 classes d'AffectNet.
FACE_MIN_CONFIDENCE = float(os.getenv("FACE_MIN_CONFIDENCE", "35.0"))
FACE_MIN_MARGIN = float(os.getenv("FACE_MIN_MARGIN", "8.0"))

# Que faire quand cette porte rejette le label alors que le point mesuré, lui,
# reste stable ? Le cas est fréquent sur un visage qui parle : l'expression
# évolue d'une image à l'autre, la distribution moyennée s'aplatit et aucune
# classe ne se détache — alors même que les points restent groupés au même
# endroit du plan (dispersion faible).
#   True (défaut) : le label est alors dérivé du point médian, comme le fait
#       déjà le canal vocal, et la fiabilité du canal est estimée sur la
#       stabilité intra-fenêtre. La fenêtre reste mesurable.
#   False : ancien comportement, la fenêtre entière est écartée.
# Sans ce repli, une porte documentée comme servant à l'AFFICHAGE opposait en
# pratique un veto au calcul, qui n'utilise pourtant que le point continu. Même
# raisonnement que pour le mode vocal "intensite" abandonné plus bas : un canal
# peu expressif n'est pas un canal peu fiable, et « sourire social + voix
# plate » est précisément le cas que le dispositif doit détecter.
FACE_LABEL_FALLBACK = os.getenv("FACE_LABEL_FALLBACK", "true").lower() != "false"

# Modèle facial : EfficientNet multi-tâches entraîné sur AffectNet, servi en
# ONNX. Il produit 8 probabilités d'émotion ET une régression valence/arousal :
# le point mesuré ne dérive donc pas du label, contrairement au moteur FER
# utilisé jusqu'à la version précédente et désormais retiré.
EMOTIEFFLIB_MODEL = os.getenv("EMOTIEFFLIB_MODEL", "enet_b0_8_va_mtl")

# Harmonisation d'échelle entre les deux canaux. La régression AffectNet est
# calibrée mais resserrée (dépasse rarement ±0.5), là où le canal vocal couvre
# pratiquement [-1, 1]. Sans ce facteur, la distance entre les deux points
# serait dominée par la voix. Ce n'est PAS un réglage de sensibilité : c'est un
# changement d'unité, à mesurer et non à deviner. L'endpoint /calibration
# propose une valeur estimée sur les distributions réellement observées.
EMOTIEFFLIB_VA_GAIN = float(os.getenv("EMOTIEFFLIB_VA_GAIN", "1.8"))

# Nombre de points (valence, arousal) conservés en mémoire par canal pour la
# calibration. Aucune image, aucun son, rien de persisté sur disque.
CALIBRATION_SAMPLE_LIMIT = int(os.getenv("CALIBRATION_SAMPLE_LIMIT", "2000"))

# Confrontation cross-modale (voir apply_cross_modal_check).
#   "desactive" (défaut) : la fiabilité de chaque canal est estimée à
#       l'intérieur de ce canal — dispersion intra-fenêtre côté visage,
#       concordance des sous-fenêtres côté voix. Jamais par comparaison avec
#       l'autre canal : ce serait circulaire, puisque le désaccord entre les
#       deux canaux est précisément l'objet de la mesure.
#   "penalite" : la fiabilité du canal visuel est réduite quand la voix le
#       contredit. Hérité de FER, dont le label était peu fiable.
#   "rejet" : ancien comportement, la fenêtre entière était supprimée.
# Les deux derniers modes sont conservés pour pouvoir mesurer leur effet.
FACE_VETO_MODE = os.getenv("FACE_VETO_MODE", "desactive").lower()
FACE_VETO_PENALTY = float(os.getenv("FACE_VETO_PENALTY", "0.5"))
FACE_VETO_ENABLED = FACE_VETO_MODE != "desactive"

# ---------------------------------------------------------------------------
# Fiabilité du canal vocal
# ---------------------------------------------------------------------------
# Le modèle vocal est une régression (valence/arousal) : il ne fournit aucune
# probabilité, donc aucune confiance native. Deux façons de l'approximer :
#
#   "stabilite" (défaut) : la fenêtre est découpée en sous-fenêtres recouvrantes
#       et le modèle est appliqué à chacune. Si les estimations concordent, la
#       mesure est fiable ; si elles divergent, elle ne l'est pas. Symétrique de
#       ce qui est fait sur le visage.
#   "intensite" (ancien) : la confiance était la distance au centre du plan.
#       Cette approche confond fiabilité et intensité émotionnelle : une voix
#       atone produisait une confiance nulle et faisait rejeter la fenêtre — or
#       « sourire social + voix plate » est une présentation typique du masquage,
#       c'est-à-dire précisément le cas que le dispositif cherche à détecter.
VOICE_CONFIDENCE_MODE = os.getenv("VOICE_CONFIDENCE_MODE", "stabilite").lower()

# Nombre de sous-fenêtres vocales par fenêtre d'analyse (recouvrement 50 %).
# 1 = une seule inférence, retour au mode "intensite" faute de dispersion.
# Coût : environ 1,5x le temps d'inférence pour 3 sous-fenêtres.
VOICE_SUBWINDOWS = int(os.getenv("VOICE_SUBWINDOWS", "3"))

# Durée minimale d'une sous-fenêtre vocale (secondes).
VOICE_SUBWINDOW_MIN_SECONDS = float(os.getenv("VOICE_SUBWINDOW_MIN_SECONDS", "1.0"))

# Dispersion vocale correspondant à une fiabilité nulle. Au-delà, les
# sous-fenêtres se contredisent trop pour qu'un point unique les résume.
VOICE_MAX_DISPERSION = float(os.getenv("VOICE_MAX_DISPERSION", "0.60"))

# Utilisé uniquement en mode "intensite" (magnitude jugée "très confiante").
VOICE_MAX_EXPECTED_MAGNITUDE = 0.5
# Aligné sur le plancher de _confidence_weight (28) pour éviter une zone morte.
SEUIL_MIN_VOIX = 28

# Seuil de dissonance : distance dans le plan valence-arousal (max ≈ 2.83).
SEUIL_DISSONANCE_DISTANCE = float(os.getenv("SEUIL_DISSONANCE_DISTANCE", "0.8"))

# Gradation de l'alerte. Ces valeurs étaient codées en dur dans
# detect_dissonance ; elles sont exposées ici car ce sont elles qu'il faut
# recalibrer sur un corpus de référence, et non le code.
#   ~0.8  incongruence entre quadrants voisins
#   ~1.5  opposition inter-quadrants
#   ~1.8+ opposition quasi diamétrale
ALERT_SEVERE_DISTANCE = float(os.getenv("ALERT_SEVERE_DISTANCE", "1.8"))
ALERT_SEVERE_CONFIDENCE = float(os.getenv("ALERT_SEVERE_CONFIDENCE", "60"))
ALERT_MODERATE_DISTANCE = float(os.getenv("ALERT_MODERATE_DISTANCE", "1.5"))
ALERT_MODERATE_CONFIDENCE = float(os.getenv("ALERT_MODERATE_CONFIDENCE", "40"))

# Seuils de valence à partir desquels la voix est considérée comme contredisant
# franchement le visage. N'ont d'effet que si FACE_VETO_MODE est activé.
VOICE_NEG_THRESHOLD = float(os.getenv("VOICE_NEG_THRESHOLD", "-0.15"))
VOICE_POS_THRESHOLD = float(os.getenv("VOICE_POS_THRESHOLD", "0.15"))
# La confrontation ne concerne que les mesures faciales peu confiantes : un
# visage franc contredit par la voix est un masquage, pas une erreur.
FACE_VETO_MAX_CONFIDENCE = float(os.getenv("FACE_VETO_MAX_CONFIDENCE", "45.0"))

# Nombre de fenêtres dissonantes exigées, sur les PERSISTENCE_WINDOW dernières,
# avant de faire vibrer la montre.
#
# PERSISTENCE_MIN = 1 : la vibration part dès la première fenêtre dissonante.
# La règle avait été introduite quand une seule image pouvait porter la
# décision : une erreur ponctuelle du classifieur suffisait alors à déclencher
# l'alerte. Ce n'est plus le cas — chaque fenêtre agrège désormais une dizaine
# d'images, résumées par une médiane et écartées si elles se dispersent trop :
# le filtrage des erreurs transitoires a lieu À L'INTÉRIEUR de la fenêtre.
# Exiger une seconde fenêtre faisait donc doublon, au prix d'un retard de trois
# secondes qui repoussait l'alerte hors du silence thérapeutique visé.
# La protection contre la fatigue d'alarme repose sur le délai réfractaire
# ci-dessous, pas sur la répétition. Monter cette valeur à 2 reste possible si
# les mesures montrent trop de fausses alertes.
PERSISTENCE_WINDOW = 3
PERSISTENCE_MIN = int(os.getenv("PERSISTENCE_MIN", "1"))

# Délai minimum entre deux vibrations. Il reste le seul rempart contre la
# fatigue d'alarme depuis que l'alerte part dès la première fenêtre : une
# dissonance qui dure ne fait donc vibrer la montre qu'une fois par intervalle,
# au lieu d'une fois par fenêtre d'analyse (environ toutes les trois secondes).
VIBRATION_COOLDOWN_SECONDS = float(os.getenv("VIBRATION_COOLDOWN_SECONDS", "5"))

# Durée du motif de vibration (délai avant de « raccrocher » l'appel simulé).
# C'est une temporisation du MOTIF, pas une latence de transmission : elle ne
# doit pas être comptée dans la latence de bout en bout.
VIBRATION_DURATION_SECONDS = float(os.getenv("VIBRATION_DURATION_SECONDS", "1.0"))

# Configuration audio
SAMPLERATE = 16000
# Périphérique loopback (None = HP par défaut). Certains casques BT/USB ne
# renvoient rien en loopback ; viser alors la carte interne (ex. Realtek Digital Output).
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", None)

# Configuration BLE - Commandes Moyoung
NOTIF_CALL = 0
NOTIF_CALL_OFF_HOOK = 0xFF