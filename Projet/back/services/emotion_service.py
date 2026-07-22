"""Détection d'émotions multimodale (visage + voix), optimisée pour le CPU."""
import logging
import base64
import os
from collections import deque
import numpy as np
import cv2
import librosa
from typing import Dict, Tuple, Optional

# fer 25.10.3 importe pkg_resources, retiré des Python récents : shim minimal.
try:
    import pkg_resources
except ImportError:
    import sys
    from importlib.metadata import version as _version

    class _DummyDistribution:
        def __init__(self, name):
            self._name = name
        @property
        def version(self):
            return _version(self._name)
    def _get_distribution(name):
        return _DummyDistribution(name)
    def _resource_filename(package, filename):
        import os
        pkg = __import__(package)
        return os.path.join(os.path.dirname(pkg.__file__), filename)
    _pkg_resources = type('obj', (object,), {
        'get_distribution': _get_distribution,
        'resource_filename': _resource_filename
    })
    sys.modules['pkg_resources'] = _pkg_resources

from fer.fer import FER
import mediapipe as mp

# Modèle vocal : sort directement (arousal, dominance, valence) en continu,
# qu'on branche sur le plan de Russell. Chargé en lazy dans _initialize_models
# pour ne pas imposer torch/transformers à l'import du module.
VOICE_MODEL_ID = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"

from config.settings import (
    EMOTION_GROUPS,
    EMOTION_COORDINATES,
    SEUIL_DISSONANCE_DISTANCE,
    VOICE_MAX_EXPECTED_MAGNITUDE,
    FACE_MIN_DETECTION_CONFIDENCE,
    FACE_MIN_SIZE_PX,
    FACE_SMOOTH_WINDOW,
    FACE_TARGET_SIZE,
    FACE_MIN_CONFIDENCE,
    FACE_MIN_MARGIN,
    VOICE_NEG_THRESHOLD,
    VOICE_POS_THRESHOLD,
    FACE_VETO_MAX_CONFIDENCE,
    FACE_ENGINE,
    EMOTIEFFLIB_MODEL,
)

# Correspondance des 8 classes EmotiEffLib (AffectNet) vers les labels internes,
# pour l'affichage et les quadrants. Le calcul de dissonance utilise, lui, la
# valence/arousal continue renvoyée nativement par le modèle.
EMOTIEFFLIB_LABEL_MAP = {
    "Anger": "angry",
    "Contempt": "disgust",
    "Disgust": "disgust",
    "Fear": "fear",
    "Happiness": "happy",
    "Neutral": "neutral",
    "Sadness": "sad",
    "Surprise": "surprise",
}

# Configuration du logging
logger = logging.getLogger(__name__)


class EmotionService:
    _instance: Optional['EmotionService'] = None
    _fer_model: Optional[FER] = None
    _mp_face_detection = None
    _voice_pipeline = None

    def __new__(cls):
        """Singleton pour garantir une seule instance du service d'émotions"""
        if cls._instance is None:
            cls._instance = super(EmotionService, cls).__new__(cls)
            cls._instance._initialize_models()
        return cls._instance

    def _initialize_models(self):
        """Initialise les modèles de détection d'émotions (MediaPipe + FER/EmotiEffLib)."""
        logger.info("Initialisation des modèles de détection d'émotions (moteur facial : %s)...", FACE_ENGINE)
        self._face_history = deque(maxlen=FACE_SMOOTH_WINDOW)
        self._face_va_history = deque(maxlen=FACE_SMOOTH_WINDOW)
        self._voice_history = deque(maxlen=3)
        self._emotiefflib = None

        # Initialisation immédiate de MediaPipe Face Detection
        model_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "models",
            "face_detector.task"
        )

        model_path = os.path.abspath(model_path)

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Modèle MediaPipe introuvable : {model_path}"
            )

        base_options = mp.tasks.BaseOptions(
            model_asset_path=model_path
        )

        options = mp.tasks.vision.FaceDetectorOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            min_detection_confidence=FACE_MIN_DETECTION_CONFIDENCE
        )

        self._mp_face_detection = mp.tasks.vision.FaceDetector.create_from_options(
            options
        )

        # Classifieur facial : FER ou EmotiEffLib selon la configuration.
        if FACE_ENGINE == "emotiefflib":
            from emotiefflib.facial_analysis import EmotiEffLibRecognizer
            # Backend ONNX : self-contained, pas de dépendance à la version de timm.
            self._emotiefflib = EmotiEffLibRecognizer(
                engine="onnx", model_name=EMOTIEFFLIB_MODEL, device="cpu"
            )
            logger.info("Modèle EmotiEffLib chargé : %s (ONNX).", EMOTIEFFLIB_MODEL)
        else:
            self._fer_model = FER(mtcnn=False)

            # MediaPipe fait déjà la détection : on court-circuite celle de FER en
            # lui renvoyant toujours l'image entière.
            def bypass_face_detection(image, **kwargs):
                h_img, w_img = image.shape[:2]
                return [(0, 0, w_img, h_img)]

            self._fer_model.find_faces = bypass_face_detection

        # Chargement du modèle vocal (lazy, pour ne pas imposer torch à l'import).
        # Ce checkpoint n'est pas chargeable via une classe AutoModel générique :
        # sa tête de régression (3 sorties) n'existe dans aucune classe standard
        # de transformers. On redéfinit donc localement la classe fournie par
        # audEERING, sinon les poids de la tête ne matchent pas et la sortie est
        # aberrante.
        try:
            import torch
            import torch.nn as nn
            from transformers import Wav2Vec2Processor
            from transformers.models.wav2vec2.modeling_wav2vec2 import (
                Wav2Vec2Model,
                Wav2Vec2PreTrainedModel,
            )

            class _RegressionHead(nn.Module):
                """Tête de régression (arousal, dominance, valence)."""

                def __init__(self, config):
                    super().__init__()
                    self.dense = nn.Linear(config.hidden_size, config.hidden_size)
                    self.dropout = nn.Dropout(config.final_dropout)
                    self.out_proj = nn.Linear(config.hidden_size, config.num_labels)

                def forward(self, features):
                    x = self.dropout(features)
                    x = torch.tanh(self.dense(x))
                    x = self.dropout(x)
                    return self.out_proj(x)

            class _EmotionModel(Wav2Vec2PreTrainedModel):
                """Backbone wav2vec2 + tête de régression continue."""

                def __init__(self, config):
                    super().__init__(config)
                    self.config = config
                    self.wav2vec2 = Wav2Vec2Model(config)
                    self.classifier = _RegressionHead(config)
                    # transformers 5.x attend post_init() (et non l'init_weights()
                    # de l'ancien tuto) : sans lui, from_pretrained échoue sur
                    # all_tied_weights_keys.
                    self.post_init()

                def forward(self, input_values):
                    hidden_states = self.wav2vec2(input_values)[0]
                    pooled = torch.mean(hidden_states, dim=1)
                    return pooled, self.classifier(pooled)

            logger.info("Chargement du modèle vocal audeering (valence/arousal)...")
            self._voice_processor = Wav2Vec2Processor.from_pretrained(VOICE_MODEL_ID)
            self._voice_model = _EmotionModel.from_pretrained(VOICE_MODEL_ID)
            self._voice_model.eval()
            if torch.cuda.is_available():
                self._voice_model.to("cuda")
            self._voice_device = "cuda" if torch.cuda.is_available() else "cpu"
            self._voice_pipeline = True  # marqueur de disponibilité
            logger.info("Modèle vocal chargé.")
        except Exception as e:
            logger.error(
                "Impossible de charger le modèle vocal audeering : %s. "
                "La détection vocale sera désactivée.",
                e,
            )
            self._voice_pipeline = None
            self._voice_model = None
            self._voice_processor = None

        logger.info("Modèles de détection d'émotions initialisés.")

    @staticmethod
    def _normalize_feature(value: float, min_value: float, max_value: float) -> float:
        """Normalise une feature numérique entre 0 et 1."""
        if max_value <= min_value:
            return 0.0
        return float(np.clip((value - min_value) / (max_value - min_value), 0.0, 1.0))

    def _smooth_emotion_scores(
        self,
        history: deque,
        scores: Dict[str, float]
    ) -> Dict[str, float]:
        """Lisse les scores d'émotions sur plusieurs fenêtres récentes."""
        history.append(scores)
        labels = {label for snapshot in history for label in snapshot.keys()}
        if not labels:
            return {}
        return {
            label: float(np.mean([snapshot.get(label, 0.0) for snapshot in history]))
            for label in labels
        }

    def _select_stable_emotion(
        self,
        scores: Dict[str, float],
        min_confidence: float,
        min_margin: float
    ) -> Tuple[Optional[str], float]:
        """
        Sélectionne une émotion seulement si elle reste suffisamment stable.
        Évite les faux positifs quand plusieurs émotions sont proches.
        """
        if not scores:
            return None, 0.0

        sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_label, best_score = sorted_scores[0]
        second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
        margin = best_score - second_score

        if best_label == "neutral":
            if best_score >= min_confidence:
                return best_label, float(best_score)
            return None, 0.0

        if best_score < min_confidence or margin < min_margin:
            return None, 0.0

        return best_label, float(best_score)

    @staticmethod
    def _distribution_to_coordinates(
        scores: Dict[str, float]
    ) -> Optional[Tuple[float, float]]:
        """
        Projette la distribution faciale complète dans le plan de Russell
        (barycentre pondéré V = Σ pi·Vi, A = Σ pi·Ai), plutôt que le seul label
        dominant. Un visage ambigu (happy ≈ sad) tombe près du centre, un visage
        franc atteint le bord — l'incertitude de FER devient une distance faible.
        """
        if not scores:
            return None
        total = sum(s for label, s in scores.items() if label in EMOTION_COORDINATES)
        if total <= 0:
            return None
        v = sum(
            EMOTION_COORDINATES[label][0] * s
            for label, s in scores.items() if label in EMOTION_COORDINATES
        ) / total
        a = sum(
            EMOTION_COORDINATES[label][1] * s
            for label, s in scores.items() if label in EMOTION_COORDINATES
        ) / total

        # Renormalisation par la probabilité dominante : le barycentre brut
        # compresse l'échelle (une distribution n'est jamais pure), ce qui
        # rapproche tout du centre. En divisant par p_top, un label certain
        # retrouve ses coordonnées de référence et les seuils restent valides.
        p_top = max(scores.values()) / total
        if p_top > 0:
            v, a = v / p_top, a / p_top
        v = float(np.clip(v, -1.0, 1.0))
        a = float(np.clip(a, -1.0, 1.0))
        return (v, a)

    def detect_face_emotion(
        self, image_base64: str
    ) -> Tuple[Optional[str], float, Optional[Tuple[float, float]]]:
        """
        Détecte l'émotion sur une image base64 : MediaPipe localise le visage,
        FER le classe.

        Returns: (label, confiance, (valence, arousal))
            - label : émotion stable, pour l'affichage et les quadrants.
            - (valence, arousal) : barycentre continu de la distribution FER,
              utilisé pour le calcul de dissonance.
        """
        try:
            # Décoder l'image base64
            img_data = base64.b64decode(image_base64)
            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                logger.warning("Impossible de décoder l'image")
                return None, 0.0, None

            # Convertir en RGB pour MediaPipe
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # Détection du visage avec MediaPipe
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=img_rgb
            )

            results = self._mp_face_detection.detect(mp_image)

            if not results.detections or len(results.detections) == 0:
                logger.debug("Aucun visage détecté")
                return None, 0.0, None

            # Prendre le visage le plus grand pour limiter les faux positifs
            detection = max(
                results.detections,
                key=lambda det: det.bounding_box.width * det.bounding_box.height
            )
            bbox = detection.bounding_box
            
            # Découper le visage avec une marge
            h, w = img.shape[:2]
            
            # Coordonnées du bounding box
            x = max(0, bbox.origin_x)
            y = max(0, bbox.origin_y)
            width = min(bbox.width, w - x)
            height = min(bbox.height, h - y)
            
            # Ajouter une marge de 20% pour être sûr d'avoir tout le visage
            margin_w = int(width * 0.2)
            margin_h = int(height * 0.2)
            x = max(0, x - margin_w)
            y = max(0, y - margin_h)
            width = min(w - x, width + 2 * margin_w)
            height = min(h - y, height + 2 * margin_h)
            
            # Découper le visage
            face_crop = img[y:y+height, x:x+width]
            
            if face_crop.size == 0:
                logger.debug("Visage découpé vide")
                return None, 0.0, None

            if width < FACE_MIN_SIZE_PX or height < FACE_MIN_SIZE_PX:
                logger.debug("Visage trop petit pour une classification fiable")
                return None, 0.0, None

            # EmotiEffLib : classification + valence/arousal native sur le crop.
            if self._emotiefflib is not None:
                return self._classify_emotiefflib(face_crop)

            # FER directement sur le crop (la détection de visage est déjà faite).
            try:
                # Égalisation de contraste (CLAHE) avant classification.
                lab = cv2.cvtColor(face_crop, cv2.COLOR_BGR2LAB)
                l_channel, a_channel, b_channel = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                l_channel = clahe.apply(l_channel)
                enhanced_face = cv2.cvtColor(
                    cv2.merge((l_channel, a_channel, b_channel)),
                    cv2.COLOR_LAB2BGR
                )

                # Niveaux de gris + resize fixe : FER est entraîné sur du gris,
                # et un resize constant stabilise les scores d'une frame à l'autre.
                gray = cv2.cvtColor(enhanced_face, cv2.COLOR_BGR2GRAY)
                resized = cv2.resize(
                    gray, (FACE_TARGET_SIZE, FACE_TARGET_SIZE), interpolation=cv2.INTER_AREA
                )
                face_input = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)

                detections = self._fer_model.detect_emotions(face_input)

                if detections:
                    emotion_scores = {
                        label: float(score * 100.0)
                        for label, score in detections[0]["emotions"].items()
                        if label in EMOTION_COORDINATES
                    }
                    smoothed_scores = self._smooth_emotion_scores(
                        self._face_history,
                        emotion_scores
                    )
                    emotion, score = self._select_stable_emotion(
                        smoothed_scores,
                        min_confidence=FACE_MIN_CONFIDENCE,
                        min_margin=FACE_MIN_MARGIN
                    )

                    # Barycentre continu de la distribution lissée : c'est lui
                    # qui alimente le calcul de dissonance, pas le label.
                    coords = self._distribution_to_coordinates(smoothed_scores)

                    if emotion:
                        logger.info(
                            "Emotion faciale détectée: %s (%.1f) | barycentre=(%.2f, %.2f) | top=%s",
                            emotion,
                            score,
                            coords[0] if coords else 0.0,
                            coords[1] if coords else 0.0,
                            sorted(smoothed_scores.items(), key=lambda item: item[1], reverse=True)[:3]
                        )
                        return emotion, score, coords

                return None, 0.0, None

            except Exception as fer_error:
                logger.warning(f"FER erreur sur visage découpé: {fer_error}")
                return None, 0.0, None

        except Exception as e:
            logger.error(f"Erreur lors de la détection faciale: {e}", exc_info=True)
            return None, 0.0, None

    def _classify_emotiefflib(
        self, face_crop_bgr: np.ndarray
    ) -> Tuple[Optional[str], float, Optional[Tuple[float, float]]]:
        """
        Classe le visage avec EmotiEffLib (modèle multi-tâches AffectNet).

        Le modèle renvoie 8 probabilités d'émotion + valence + arousal. On garde
        le label dominant (affichage/quadrant) et surtout la valence/arousal
        CONTINUE, alignée sur le plan de Russell comme la sortie du modèle vocal.
        """
        try:
            face_rgb = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2RGB)
            labels, scores = self._emotiefflib.predict_emotions(face_rgb, logits=False)
            scores = np.asarray(scores)[0]

            # Les 2 dernières valeurs sont (valence, arousal), déjà dans [-1, 1].
            valence = float(np.clip(scores[-2], -1.0, 1.0))
            arousal = float(np.clip(scores[-1], -1.0, 1.0))

            # Confiance = probabilité du label dominant (0-100).
            emotion_probs = scores[:-2]
            score = float(np.max(emotion_probs) * 100.0)
            raw_label = labels[0] if labels else None
            emotion = EMOTIEFFLIB_LABEL_MAP.get(raw_label)

            # Lissage temporel de la valence/arousal, comme pour le visage FER.
            self._face_va_history.append((valence, arousal))
            valence = float(np.mean([v for v, _ in self._face_va_history]))
            arousal = float(np.mean([a for _, a in self._face_va_history]))

            if not emotion or score < FACE_MIN_CONFIDENCE:
                return None, 0.0, None

            logger.info(
                "Emotion faciale (EmotiEffLib): %s (%.1f) | valence=%.2f arousal=%.2f",
                emotion, score, valence, arousal,
            )
            return emotion, score, (valence, arousal)

        except Exception as e:
            logger.error("Erreur EmotiEffLib: %s", e, exc_info=True)
            return None, 0.0, None

    def detect_audio_emotion(
        self, audio_data: np.ndarray, sample_rate: int
    ) -> Tuple[Optional[str], float, Optional[Tuple[float, float]]]:
        """
        Détecte l'émotion vocale sur l'audio brut via le modèle audeering, qui
        renvoie directement un point (valence, arousal) continu.

        Returns: (label_proche, confiance, (valence, arousal))
            label_proche sert seulement à l'affichage ; le calcul de dissonance
            utilise le point continu.
        """
        try:
            # Mono + normalisation (éviter les dépassements)
            if len(audio_data.shape) > 1:
                audio_data = np.mean(audio_data, axis=1)

            max_amp = float(np.max(np.abs(audio_data)))
            if max_amp > 0:
                audio_normalized = audio_data / max_amp
            else:
                audio_normalized = audio_data

            # Rejet du silence
            energy = float(np.mean(audio_normalized ** 2))
            if energy < 0.0001:
                logger.info("Audio trop silencieux pour detecter une emotion (energie=%.6f)", energy)
                return None, 0.0, None

            # Rejet de l'audio saturé (clipping)
            clipped_ratio = float(np.mean(np.abs(audio_normalized) > 0.99))
            if clipped_ratio > 0.35:
                logger.info("Audio trop sature pour une emotion vocale fiable (clipped_ratio=%.3f)", clipped_ratio)
                return None, 0.0, None

            if self._voice_pipeline is None or self._voice_model is None:
                logger.warning("Modèle vocal indisponible, retour None")
                return None, 0.0, None

            # Le modèle attend du 16 kHz ; SAMPLERATE l'est déjà, ce resample
            # n'est qu'un garde-fou.
            TARGET_SR = 16000
            if sample_rate and sample_rate != TARGET_SR:
                audio_for_model = librosa.resample(
                    audio_normalized.astype(np.float32),
                    orig_sr=sample_rate,
                    target_sr=TARGET_SR,
                )
            else:
                audio_for_model = audio_normalized.astype(np.float32)

            import torch
            try:
                inputs = self._voice_processor(audio_for_model, sampling_rate=TARGET_SR)
                input_values = inputs["input_values"][0]
                input_values = np.asarray(input_values).reshape(1, -1)
                input_tensor = torch.from_numpy(input_values).to(self._voice_device)
                with torch.no_grad():
                    _, logits = self._voice_model(input_tensor)
                # Ordre de sortie du modèle : arousal, dominance, valence.
                arousal_raw, dominance_raw, valence_raw = logits.squeeze().cpu().numpy().tolist()
            except Exception as infer_err:
                logger.warning("Echec inference vocale: %s", infer_err)
                return None, 0.0, None

            # Sortie ~[0, 1] (0.5 = neutre) reprojetée sur [-1, 1] (plan de Russell).
            valence = float(np.clip((valence_raw - 0.5) * 2.0, -1.0, 1.0))
            arousal = float(np.clip((arousal_raw - 0.5) * 2.0, -1.0, 1.0))

            # Pas de confiance native (régression) : on prend la distance au
            # centre comme proxy, normalisée par VOICE_MAX_EXPECTED_MAGNITUDE.
            magnitude = float(np.sqrt(valence ** 2 + arousal ** 2))
            confidence = float(np.clip(magnitude / VOICE_MAX_EXPECTED_MAGNITUDE, 0.0, 1.0) * 100.0)

            # Lissage temporel léger, comme pour le visage.
            self._voice_history.append({"valence": valence, "arousal": arousal, "confidence": confidence})
            valence = float(np.mean([s["valence"] for s in self._voice_history]))
            arousal = float(np.mean([s["arousal"] for s in self._voice_history]))
            confidence = float(np.mean([s["confidence"] for s in self._voice_history]))

            # Label le plus proche, pour l'affichage uniquement.
            nearest_label, nearest_dist = None, None
            for label, (v_ref, a_ref) in EMOTION_COORDINATES.items():
                dist = float(np.sqrt((valence - v_ref) ** 2 + (arousal - a_ref) ** 2))
                if nearest_dist is None or dist < nearest_dist:
                    nearest_label, nearest_dist = label, dist

            logger.info(
                "Voix: valence=%.2f arousal=%.2f confiance=%.1f (~%s) [brut arousal=%.2f dominance=%.2f valence=%.2f]",
                valence, arousal, confidence, nearest_label,
                arousal_raw, dominance_raw, valence_raw,
            )

            return nearest_label, confidence, (valence, arousal)

        except Exception as e:
            logger.error(f"Erreur lors de la detection audio: {e}", exc_info=True)
            return None, 0.0, None

    def get_emotion_quadrant(self, emotion: str) -> Optional[str]:
        """
        Récupère le quadrant (modèle Russell) d'une émotion donnée.
        """
        for quadrant, emotions in EMOTION_GROUPS.items():
            if emotion.lower() in [e.lower() for e in emotions]:
                return quadrant
        return None

    def get_emotion_coordinates(self, emotion: str) -> Optional[Tuple[float, float]]:
        """
        Récupère les coordonnées (valence, arousal) d'une émotion (modèle Russell).
        """
        return EMOTION_COORDINATES.get(emotion.lower(), None)

    def calculate_emotion_distance(
        self,
        emotion1: str,
        emotion2: str
    ) -> Optional[float]:
        """
        Calcule la distance euclidienne entre deux émotions dans le plan valence-arousal.
        Référence : Modèle circumplex de Russell (1980)
        """
        coord1 = self.get_emotion_coordinates(emotion1)
        coord2 = self.get_emotion_coordinates(emotion2)
        
        if not coord1 or not coord2:
            return None
        
        # Distance euclidienne : √[(v1 - v2)² + (a1 - a2)²]
        valence_diff = coord1[0] - coord2[0]
        arousal_diff = coord1[1] - coord2[1]
        distance = np.sqrt(valence_diff ** 2 + arousal_diff ** 2)
        
        return float(distance)

    @staticmethod
    def _confidence_weight(score: float, floor: float = 28.0, ceil: float = 90.0) -> float:
        """
        Confiance brute d'un canal (0-100) -> poids de fusion (0-1). Sous le
        plancher : 0 (flux inexploitable). Au-dessus du plafond : 1.
        """
        if score <= floor:
            return 0.0
        if score >= ceil:
            return 1.0
        return float((score - floor) / (ceil - floor))

    @staticmethod
    def _fuzzy_dissonance_membership(distance: float) -> float:
        """
        Degré d'appartenance flou de la distance à la classe "dissonance" :
        0 sous le seuil, montée linéaire jusqu'à 1 à la demi-diagonale (~1.8).
        Remplace un déclenchement binaire par une gradation continue.
        """
        low = SEUIL_DISSONANCE_DISTANCE
        high = 1.8
        if distance <= low:
            return 0.0
        if distance >= high:
            return 1.0
        return float((distance - low) / (high - low))

    def reconcile_face_emotion(
        self,
        face_emotion: Optional[str],
        voice_coordinates: Optional[Tuple[float, float]],
        face_score: float = 0.0,
    ) -> Optional[str]:
        """
        Neutralise le label facial quand la voix le contredit franchement
        (FER confond happy/sad dans les deux sens, la voix est le canal le plus
        fiable). Un label confiant (>= FACE_VETO_MAX_CONFIDENCE) n'est jamais
        touché : c'est le cas du masquage, la dissonance qu'on veut détecter.
        """
        if not face_emotion or not voice_coordinates:
            return face_emotion

        if face_score >= FACE_VETO_MAX_CONFIDENCE:
            return face_emotion

        quadrant = self.get_emotion_quadrant(face_emotion)
        if not quadrant:
            return face_emotion

        face_is_positive = quadrant.startswith("Q1") or quadrant.startswith("Q2")
        face_is_negative = quadrant.startswith("Q3") or quadrant.startswith("Q4")
        valence_voix = voice_coordinates[0]

        if face_is_positive and valence_voix < VOICE_NEG_THRESHOLD:
            logger.info(
                "Correction cross-modale : visage '%s' (positif) contredit par "
                "une voix négative (valence=%.2f) -> label neutralisé",
                face_emotion, valence_voix,
            )
            return None

        if face_is_negative and valence_voix > VOICE_POS_THRESHOLD:
            logger.info(
                "Correction cross-modale : visage '%s' (négatif) contredit par "
                "une voix positive (valence=%.2f) -> label neutralisé",
                face_emotion, valence_voix,
            )
            return None

        return face_emotion

    def detect_dissonance(
        self,
        face_emotion: Optional[str],
        face_score: float,
        voice_emotion: Optional[str],
        voice_score: float,
        voice_coordinates: Optional[Tuple[float, float]] = None,
        face_coordinates: Optional[Tuple[float, float]] = None,
    ) -> Tuple[bool, float, str, float]:
        """
        Détecte la dissonance émotionnelle entre le visage et la voix :
          1. Projection des deux canaux dans le plan de Russell (valence, arousal).
          2. Distance euclidienne D entre les deux points.
          3. Degré flou de D (au lieu d'un seuil binaire).
          4. Fusion pondérée par la confiance de chaque canal.

        voice_coordinates / face_coordinates : points continus des deux canaux ;
        à défaut, repli sur les coordonnées du label.

        Returns: (is_dissonant, confidence, alert_level, emotion_distance)
        """
        if not face_emotion or not voice_emotion:
            return False, 0.0, "NONE", 0.0

        quadrant_face = self.get_emotion_quadrant(face_emotion)
        quadrant_voice = self.get_emotion_quadrant(voice_emotion)

        if not quadrant_face or not quadrant_voice:
            return False, 0.0, "NONE", 0.0

        # Distance euclidienne dans le plan de Russell. face_coordinates est le
        # barycentre continu du visage (sinon repli sur les coords du label).
        face_coords = face_coordinates or self.get_emotion_coordinates(face_emotion)
        if face_coords and voice_coordinates:
            emotion_distance = float(np.sqrt(
                (face_coords[0] - voice_coordinates[0]) ** 2
                + (face_coords[1] - voice_coordinates[1]) ** 2
            ))
        else:
            emotion_distance = self.calculate_emotion_distance(face_emotion, voice_emotion) or 0.0

        # Degré flou d'incongruence.
        fuzzy_mu = self._fuzzy_dissonance_membership(emotion_distance)

        # Pondération par la confiance des deux canaux.
        w_f = self._confidence_weight(face_score)
        w_v = self._confidence_weight(voice_score)
        weight_sum = w_f + w_v
        if weight_sum < 0.2:
            # Aucun canal assez confiant : pas de fusion fiable.
            return False, 0.0, "NONE", emotion_distance

        # Confiance pondérée modulée par le degré flou (0-100).
        confidence = float(
            (w_f * face_score + w_v * voice_score) / weight_sum * fuzzy_mu
        )

        # fuzzy_mu=0 (sous le seuil de distance) donne confidence=0.
        is_dissonant = confidence > 0.0

        # Gradation par distance / confiance :
        #   ~0.8  incongruence (quadrants voisins)
        #   ~1.5  opposition inter-quadrants
        #   ~1.8+ opposition quasi diamétrale
        alert_level = "NONE"
        if is_dissonant:
            if emotion_distance >= 1.8 or confidence >= 60:
                alert_level = "SEVERE"
            elif emotion_distance >= 1.5 or confidence >= 40:
                alert_level = "MODERATE"
            else:
                alert_level = "VIGILANCE"

        return is_dissonant, round(confidence, 1), alert_level, emotion_distance


# Instance singleton du service d'émotions
emotion_service = EmotionService()