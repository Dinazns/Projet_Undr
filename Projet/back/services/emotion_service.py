"""Détection d'émotions multimodale (visage + voix), optimisée pour le CPU.

Les deux canaux produisent nativement un point continu (valence, arousal) dans
le plan de Russell :

  - Visage : EmotiEffLib (EfficientNet multi-tâches entraîné sur AffectNet), qui
    renvoie 8 probabilités d'émotion ET une régression valence/arousal.
  - Voix   : audeering wav2vec2, qui renvoie une régression (arousal, dominance,
    valence).

Conséquence importante : la table de coordonnées universelles par émotion
(EMOTION_COORDINATES) n'intervient plus dans la mesure. Elle ne sert qu'à
nommer le point le plus proche pour l'affichage. Le postulat d'une
correspondance universelle « une émotion = des coordonnées fixes », contesté par
la théorie de l'émotion construite, a donc quitté le chemin de calcul.
"""
import logging
import base64
import os
import time
from collections import deque
import numpy as np
import cv2
import librosa
from typing import Any, Dict, List, Optional, Tuple, Union

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
    FACE_MIN_CONFIDENCE,
    FACE_MIN_MARGIN,
    FACE_LABEL_FALLBACK,
    FACE_MAX_DISPERSION,
    VOICE_NEG_THRESHOLD,
    VOICE_POS_THRESHOLD,
    FACE_VETO_MAX_CONFIDENCE,
    EMOTIEFFLIB_MODEL,
    EMOTIEFFLIB_VA_GAIN,
    VOICE_SMOOTH_WINDOW,
    FACE_VETO_MODE,
    FACE_VETO_PENALTY,
    VOICE_CONFIDENCE_MODE,
    VOICE_SUBWINDOWS,
    VOICE_SUBWINDOW_MIN_SECONDS,
    VOICE_MAX_DISPERSION,
    ALERT_SEVERE_DISTANCE,
    ALERT_SEVERE_CONFIDENCE,
    ALERT_MODERATE_DISTANCE,
    ALERT_MODERATE_CONFIDENCE,
    CALIBRATION_SAMPLE_LIMIT,
)

# Correspondance des 8 classes EmotiEffLib (AffectNet) vers les labels internes.
# Sert uniquement à l'affichage : le calcul utilise la valence/arousal continue.
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

logger = logging.getLogger(__name__)

# Bornes de conversion « fiabilité brute (0-100) -> poids de fusion (0-1) ».
# Sous le plancher, le canal est considéré inexploitable.
CONFIDENCE_FLOOR = 28.0
CONFIDENCE_CEIL = 90.0


class EmotionService:
    _instance: Optional['EmotionService'] = None
    _mp_face_detection = None
    _voice_pipeline = None

    def __new__(cls):
        """Singleton pour garantir une seule instance du service d'émotions"""
        if cls._instance is None:
            cls._instance = super(EmotionService, cls).__new__(cls)
            cls._instance._initialize_models()
        return cls._instance

    def _initialize_models(self):
        """Initialise MediaPipe (détection), EmotiEffLib (visage) et wav2vec2 (voix)."""
        logger.info("Initialisation des modèles de détection d'émotions...")

        # Historiques INTER-fenêtres. Par défaut maxlen=1, c'est-à-dire aucun
        # lissage : l'agrégation se fait à l'intérieur de la fenêtre d'analyse,
        # sur le même intervalle que le canal vocal.
        self._face_history = deque(maxlen=max(1, FACE_SMOOTH_WINDOW))
        self._face_va_history = deque(maxlen=max(1, FACE_SMOOTH_WINDOW))
        self._voice_history = deque(maxlen=max(1, VOICE_SMOOTH_WINDOW))

        # Échantillons bruts conservés pour la calibration d'échelle inter-canaux
        # (voir get_calibration_stats). Aucune image, aucun son : uniquement des
        # couples (valence, arousal) anonymes, en mémoire, jamais persistés.
        self._calib_face = deque(maxlen=CALIBRATION_SAMPLE_LIMIT)
        self._calib_voice = deque(maxlen=CALIBRATION_SAMPLE_LIMIT)

        # Nombre de sous-fenêtres vocales de la dernière analyse. En dessous de
        # deux, la fiabilité par concordance est impossible et le service
        # retombe sur l'ancien mode « intensité » : il faut pouvoir le constater.
        self.last_voice_subwindows = 0

        # --- Détection de visage : MediaPipe Face Detection ---
        model_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "models", "face_detector.task")
        )
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Modèle MediaPipe introuvable : {model_path}. "
                "Lancez `python download_model.py` depuis le dossier back/."
            )

        base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
        options = mp.tasks.vision.FaceDetectorOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            min_detection_confidence=FACE_MIN_DETECTION_CONFIDENCE,
        )
        self._mp_face_detection = mp.tasks.vision.FaceDetector.create_from_options(options)

        # --- Classification faciale : EmotiEffLib ---
        # Backend ONNX : self-contained, pas de dépendance à la version de timm.
        from emotiefflib.facial_analysis import EmotiEffLibRecognizer

        self._emotiefflib = EmotiEffLibRecognizer(
            engine="onnx", model_name=EMOTIEFFLIB_MODEL, device="cpu"
        )
        logger.info("Modèle facial EmotiEffLib chargé : %s (ONNX).", EMOTIEFFLIB_MODEL)

        # --- Modèle vocal (lazy, pour ne pas imposer torch à l'import) ---
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

    # ------------------------------------------------------------------
    # Outils communs
    # ------------------------------------------------------------------

    def _smooth_emotion_scores(
        self, history: deque, scores: Dict[str, float]
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
        self, scores: Dict[str, float], min_confidence: float, min_margin: float
    ) -> Tuple[Optional[str], float]:
        """
        Sélectionne un label seulement s'il domine nettement le second.

        Ce label ne sert qu'à l'affichage et aux quadrants : le calcul de
        dissonance utilise le point continu, pas le label.
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
    def quadrant_from_coords(coords: Optional[Tuple[float, float]]) -> Optional[str]:
        """
        Quadrant de Russell déduit directement du point mesuré.

        Préféré à get_emotion_quadrant(label) : le label et le point sont deux
        sorties distinctes du même réseau multi-tâches et peuvent se contredire.
        Déduire le quadrant du point supprime cette incohérence possible.
        """
        if not coords:
            return None
        valence, arousal = coords
        if abs(valence) < 0.05 and abs(arousal) < 0.05:
            return "Q5 (Neutre)"
        if valence >= 0:
            return "Q1 (Actif/Positif)" if arousal >= 0 else "Q2 (Calme/Positif)"
        return "Q4 (Actif/Négatif)" if arousal >= 0 else "Q3 (Passif/Négatif)"

    # ------------------------------------------------------------------
    # Canal visuel
    # ------------------------------------------------------------------

    def analyze_face_frame(
        self, image: Union[str, bytes, np.ndarray]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyse UNE image du HUD, sans aucun lissage temporel.

        Appelée plusieurs fois par fenêtre d'analyse : la sélection du label et
        le lissage se font au niveau de la fenêtre, dans aggregate_face_window().
        C'est cette séparation qui permet au canal visuel de couvrir le même
        intervalle que le canal vocal, au lieu d'un instantané pris à la fin de
        la fenêtre audio.

        Args:
            image: image BGR (ndarray), ou chaîne base64 d'une image encodée.
                La boucle d'analyse passe directement le ndarray : encoder puis
                décoder dans le même processus coûtait du CPU et ajoutait une
                compression supplémentaire au signal analysé.

        Returns: {"scores", "coords", "coords_raw", "coherent", "ts"} ou None si
                 aucun visage exploitable sur cette image.
        """
        try:
            if isinstance(image, np.ndarray):
                img = image
            else:
                nparr = np.frombuffer(base64.b64decode(image), np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None or getattr(img, "size", 0) == 0:
                logger.warning("Image de capture illisible")
                return None

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
            results = self._mp_face_detection.detect(mp_image)

            if not results.detections or len(results.detections) == 0:
                logger.debug("Aucun visage détecté")
                return None

            # Visage le plus grand, pour limiter les faux positifs.
            detection = max(
                results.detections,
                key=lambda det: det.bounding_box.width * det.bounding_box.height,
            )
            bbox = detection.bounding_box

            h, w = img.shape[:2]
            x = max(0, bbox.origin_x)
            y = max(0, bbox.origin_y)
            width = min(bbox.width, w - x)
            height = min(bbox.height, h - y)

            # Marge de 20 % pour ne pas rogner le front et le menton.
            margin_w = int(width * 0.2)
            margin_h = int(height * 0.2)
            x = max(0, x - margin_w)
            y = max(0, y - margin_h)
            width = min(w - x, width + 2 * margin_w)
            height = min(h - y, height + 2 * margin_h)

            face_crop = img[y:y + height, x:x + width]

            if face_crop.size == 0:
                logger.debug("Visage découpé vide")
                return None

            if width < FACE_MIN_SIZE_PX or height < FACE_MIN_SIZE_PX:
                logger.debug("Visage trop petit pour une classification fiable")
                return None

            return self._classify_face(face_crop)

        except Exception as e:
            logger.error("Erreur lors de l'analyse faciale: %s", e, exc_info=True)
            return None

    def _classify_face(self, face_crop_bgr: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        Classe UNE image avec EmotiEffLib (EfficientNet multi-tâches AffectNet).

        Le modèle renvoie 8 probabilités d'émotion ET une régression
        valence/arousal. La librairie n'applique le softmax qu'aux 8 premières
        colonnes : les deux dernières restent les sorties brutes de la tête de
        régression. Aucun lissage ici, il est fait au niveau de la fenêtre.
        """
        try:
            face_rgb = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2RGB)
            labels, scores = self._emotiefflib.predict_emotions(face_rgb, logits=False)
            scores = np.asarray(scores)[0]

            # Deux dernières valeurs : (valence, arousal) bruts.
            valence_raw = float(scores[-2])
            arousal_raw = float(scores[-1])

            # Harmonisation d'échelle inter-canaux. La régression AffectNet est
            # calibrée mais resserrée (dépasse rarement ±0.5), là où le canal
            # vocal couvre pratiquement [-1, 1]. Sans ce facteur, la distance
            # entre les deux points serait dominée par la voix. La valeur doit
            # être calibrée sur les distributions observées : voir l'endpoint
            # /calibration, qui en propose une estimée sur les données réelles.
            valence = float(np.clip(valence_raw * EMOTIEFFLIB_VA_GAIN, -1.0, 1.0))
            arousal = float(np.clip(arousal_raw * EMOTIEFFLIB_VA_GAIN, -1.0, 1.0))

            # Distribution complète des 8 classes, conservée pour que la marge
            # top-1 / top-2 ait un sens au niveau de la fenêtre.
            emotion_probs = scores[:-2]
            emotion_scores: Dict[str, float] = {}
            for idx, raw_label in self._emotiefflib.idx_to_emotion_class.items():
                mapped = EMOTIEFFLIB_LABEL_MAP.get(raw_label)
                if mapped is None or idx >= len(emotion_probs):
                    continue
                # Contempt et Disgust partagent un même label interne : on garde
                # la probabilité la plus forte des deux.
                value = float(emotion_probs[idx] * 100.0)
                emotion_scores[mapped] = max(emotion_scores.get(mapped, 0.0), value)

            if not emotion_scores:
                return None

            top_label = EMOTIEFFLIB_LABEL_MAP.get(labels[0]) if labels else None

            # Cohérence intra-canal : le label vient de l'argmax des 8 classes,
            # le point de la tête de régression. Deux sorties du même réseau, qui
            # peuvent se contredire. Comptée par fenêtre plutôt que journalisée
            # image par image.
            quadrant = self.quadrant_from_coords((valence, arousal)) or ""
            point_positive = quadrant.startswith("Q1") or quadrant.startswith("Q2")
            label_quadrant = self.get_emotion_quadrant(top_label) if top_label else ""
            label_positive = bool(label_quadrant) and (
                label_quadrant.startswith("Q1") or label_quadrant.startswith("Q2")
            )
            neutral_zone = quadrant.startswith("Q5") or top_label == "neutral"
            coherent = neutral_zone or (point_positive == label_positive)

            self._calib_face.append((valence_raw, arousal_raw))

            return {
                "scores": emotion_scores,
                "coords": (valence, arousal),
                "coords_raw": (valence_raw, arousal_raw),
                "coherent": coherent,
                "ts": time.monotonic(),
            }

        except Exception as e:
            logger.error("Erreur EmotiEffLib: %s", e, exc_info=True)
            return None

    @staticmethod
    def _nearest_emotion_label(coords: Tuple[float, float]) -> Optional[str]:
        """
        Émotion de référence la plus proche d'un point du plan de Russell.

        Sert à nommer un point pour l'affichage et les quadrants, jamais au
        calcul de dissonance qui, lui, travaille directement sur les
        coordonnées. Utilisé par les deux canaux.
        """
        nearest_label, nearest_dist = None, None
        for label, (v_ref, a_ref) in EMOTION_COORDINATES.items():
            dist = float(np.hypot(coords[0] - v_ref, coords[1] - a_ref))
            if nearest_dist is None or dist < nearest_dist:
                nearest_label, nearest_dist = label, dist
        return nearest_label

    def aggregate_face_window(
        self, samples: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], float, Optional[Tuple[float, float]], Optional[float], int]:
        """
        Résume en un point unique les images d'UNE fenêtre d'analyse.

        Le canal visuel décrit ainsi le même intervalle que le canal vocal.

        - label / confiance : moyenne des distributions sur la fenêtre, puis
          porte de stabilité (confiance minimale et marge sur le 2e label).
        - point (valence, arousal) : médiane composante par composante, plus
          robuste qu'une moyenne à une image aberrante (visage mal cadré, flou
          de compression, clignement).
        - dispersion : distance moyenne des images à cette médiane. Élevée, elle
          signale que le visage a trop varié pour être résumé par un point : la
          fenêtre est alors écartée par l'appelant.

        Returns: (label, confiance, (valence, arousal), dispersion, n_images)
        """
        n = len(samples)
        if n == 0:
            return None, 0.0, None, None, 0

        labels = {label for s in samples for label in s["scores"]}
        mean_scores = {
            label: float(np.mean([s["scores"].get(label, 0.0) for s in samples]))
            for label in labels
        }

        # Lissage INTER-fenêtres, désactivé par défaut (FACE_SMOOTH_WINDOW = 1).
        if FACE_SMOOTH_WINDOW > 1:
            mean_scores = self._smooth_emotion_scores(self._face_history, mean_scores)

        emotion, score = self._select_stable_emotion(
            mean_scores, min_confidence=FACE_MIN_CONFIDENCE, min_margin=FACE_MIN_MARGIN
        )

        pts = np.array([s["coords"] for s in samples], dtype=np.float32)
        median = np.median(pts, axis=0)
        dispersion = float(np.mean(np.linalg.norm(pts - median, axis=1)))
        coords = (float(median[0]), float(median[1]))

        if FACE_SMOOTH_WINDOW > 1:
            self._face_va_history.append(coords)
            coords = (
                float(np.mean([c[0] for c in self._face_va_history])),
                float(np.mean([c[1] for c in self._face_va_history])),
            )

        incoherent = sum(1 for s in samples if not s.get("coherent", True))
        if incoherent:
            logger.info(
                "Incohérence intra-canal sur %d/%d image(s) : le label facial et la "
                "valence issue du même réseau ne s'accordent pas.",
                incoherent, n,
            )

        # Le classifieur n'a pas dégagé de label dominant : sur un visage qui
        # parle, l'expression bouge et la distribution moyennée s'aplatit. Si le
        # POINT, lui, est resté groupé, la fenêtre reste parfaitement mesurable :
        # on nomme le point par son émotion de référence la plus proche et on
        # estime la fiabilité du canal sur sa stabilité, comme pour la voix.
        derived = False
        if emotion is None and FACE_LABEL_FALLBACK and dispersion <= FACE_MAX_DISPERSION:
            emotion = self._nearest_emotion_label(coords)
            score = float(
                np.clip(1.0 - dispersion / FACE_MAX_DISPERSION, 0.0, 1.0) * 100.0
            )
            derived = True

        logger.info(
            "Fenêtre visage : %d image(s) | %s (%.1f)%s | médiane=(%.2f, %.2f) | "
            "dispersion=%.2f | incohérentes=%d",
            n, emotion, score, " [label dérivé du point]" if derived else "",
            coords[0], coords[1], dispersion, incoherent,
        )
        return emotion, score, coords, dispersion, n

    # ------------------------------------------------------------------
    # Réinitialisation d'état (ruptures de contexte)
    # ------------------------------------------------------------------

    def reset_face_state(self) -> None:
        """Purge la mémoire du canal visuel."""
        self._face_history.clear()
        self._face_va_history.clear()

    def reset_voice_state(self) -> None:
        """Purge la mémoire du canal vocal."""
        self._voice_history.clear()

    def reset_state(self) -> None:
        """
        Purge les deux canaux. À appeler sur changement de séquence ou de
        séance : sans cela, le premier visage d'une nouvelle scène est comparé
        à la voix de la scène précédente encore présente en mémoire.
        """
        self.reset_face_state()
        self.reset_voice_state()
        logger.info("Mémoire des deux canaux réinitialisée.")

    # ------------------------------------------------------------------
    # Canal vocal
    # ------------------------------------------------------------------

    def _split_voice_subwindows(
        self, audio: np.ndarray, sample_rate: int
    ) -> List[np.ndarray]:
        """
        Découpe la fenêtre audio en sous-fenêtres recouvrantes (50 %).

        n sous-fenêtres de longueur 2L/(n+1), décalées de la moitié de cette
        longueur, couvrent exactement la fenêtre. La concordance de leurs
        estimations sert ensuite d'indice de fiabilité de la mesure vocale.
        """
        n = max(1, VOICE_SUBWINDOWS)
        total = len(audio)
        min_len = int(VOICE_SUBWINDOW_MIN_SECONDS * sample_rate)
        if n == 1 or total < 2 * min_len:
            return [audio]

        sub_len = int(2 * total / (n + 1))
        if sub_len < min_len:
            return [audio]

        hop = sub_len // 2
        chunks = []
        for i in range(n):
            start = i * hop
            end = start + sub_len
            if end > total:
                end = total
                start = max(0, end - sub_len)
            chunk = audio[start:end]
            if len(chunk) >= min_len:
                chunks.append(chunk)
        return chunks or [audio]

    def _infer_voice_point(
        self, audio_chunk: np.ndarray, sample_rate: int
    ) -> Optional[Tuple[float, float]]:
        """Une inférence vocale -> point (valence, arousal) dans [-1, 1]."""
        import torch
        try:
            inputs = self._voice_processor(audio_chunk, sampling_rate=sample_rate)
            input_values = np.asarray(inputs["input_values"][0]).reshape(1, -1)
            input_tensor = torch.from_numpy(input_values).to(self._voice_device)
            with torch.no_grad():
                _, logits = self._voice_model(input_tensor)
            # Ordre de sortie du modèle : arousal, dominance, valence.
            arousal_raw, _dominance_raw, valence_raw = logits.squeeze().cpu().numpy().tolist()
        except Exception as infer_err:
            logger.warning("Echec inference vocale: %s", infer_err)
            return None

        # Sortie ~[0, 1] (0.5 = neutre) reprojetée sur [-1, 1] (plan de Russell).
        valence = float(np.clip((valence_raw - 0.5) * 2.0, -1.0, 1.0))
        arousal = float(np.clip((arousal_raw - 0.5) * 2.0, -1.0, 1.0))
        return valence, arousal

    def detect_audio_emotion(
        self, audio_data: np.ndarray, sample_rate: int
    ) -> Tuple[Optional[str], float, Optional[Tuple[float, float]]]:
        """
        Analyse la fenêtre audio via le modèle audeering, qui renvoie un point
        (valence, arousal) continu.

        La fenêtre est découpée en sous-fenêtres recouvrantes et la CONCORDANCE
        de leurs estimations sert d'indice de fiabilité. C'est ce qui remplace
        l'ancienne confiance fondée sur l'intensité : cette dernière confondait
        fiabilité et amplitude émotionnelle, et rejetait donc les voix atones —
        c'est-à-dire une partie des masquages que le dispositif recherche.

        Returns: (label_proche, fiabilité, (valence, arousal))
            label_proche sert uniquement à l'affichage.
        """
        try:
            # Mono + normalisation (éviter les dépassements)
            if len(audio_data.shape) > 1:
                audio_data = np.mean(audio_data, axis=1)

            max_amp = float(np.max(np.abs(audio_data)))
            audio_normalized = audio_data / max_amp if max_amp > 0 else audio_data

            # Rejet du silence
            energy = float(np.mean(audio_normalized ** 2))
            if energy < 0.0001:
                logger.info(
                    "Audio trop silencieux pour detecter une emotion (energie=%.6f)", energy
                )
                return None, 0.0, None

            # Rejet de l'audio saturé (clipping)
            clipped_ratio = float(np.mean(np.abs(audio_normalized) > 0.99))
            if clipped_ratio > 0.35:
                logger.info(
                    "Audio trop sature pour une emotion vocale fiable (clipped_ratio=%.3f)",
                    clipped_ratio,
                )
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

            chunks = self._split_voice_subwindows(audio_for_model, TARGET_SR)
            points = [
                p for p in (self._infer_voice_point(c, TARGET_SR) for c in chunks) if p
            ]
            self.last_voice_subwindows = len(points)
            if not points:
                return None, 0.0, None

            pts = np.array(points, dtype=np.float32)
            median = np.median(pts, axis=0)
            valence, arousal = float(median[0]), float(median[1])
            dispersion = float(np.mean(np.linalg.norm(pts - median, axis=1)))

            if VOICE_CONFIDENCE_MODE == "intensite" or len(points) < 2:
                # Ancien mode : la « confiance » était l'intensité émotionnelle.
                magnitude = float(np.sqrt(valence ** 2 + arousal ** 2))
                confidence = float(
                    np.clip(magnitude / VOICE_MAX_EXPECTED_MAGNITUDE, 0.0, 1.0) * 100.0
                )
            else:
                # Fiabilité = concordance des sous-fenêtres, indépendante de
                # l'intensité : une voix atone estimée trois fois de la même
                # façon est une mesure fiable, pas une mesure douteuse.
                confidence = float(
                    np.clip(1.0 - dispersion / VOICE_MAX_DISPERSION, 0.0, 1.0) * 100.0
                )

            self._calib_voice.append((valence, arousal))

            # Lissage INTER-fenêtres (désactivé par défaut, VOICE_SMOOTH_WINDOW = 1).
            self._voice_history.append(
                {"valence": valence, "arousal": arousal, "confidence": confidence}
            )
            valence = float(np.mean([s["valence"] for s in self._voice_history]))
            arousal = float(np.mean([s["arousal"] for s in self._voice_history]))
            confidence = float(np.mean([s["confidence"] for s in self._voice_history]))

            # Label le plus proche, pour l'affichage uniquement.
            nearest_label = self._nearest_emotion_label((valence, arousal))

            logger.info(
                "Fenêtre voix : %d sous-fenêtre(s) | valence=%.2f arousal=%.2f | "
                "dispersion=%.2f | fiabilité=%.1f (mode %s) (~%s)",
                len(points), valence, arousal, dispersion, confidence,
                VOICE_CONFIDENCE_MODE, nearest_label,
            )

            return nearest_label, confidence, (valence, arousal)

        except Exception as e:
            logger.error(f"Erreur lors de la detection audio: {e}", exc_info=True)
            return None, 0.0, None

    # ------------------------------------------------------------------
    # Référentiel de Russell (affichage uniquement)
    # ------------------------------------------------------------------

    def get_emotion_quadrant(self, emotion: Optional[str]) -> Optional[str]:
        """
        Quadrant associé à un LABEL. Conservé pour l'affichage et la
        compatibilité ; le chemin de mesure utilise quadrant_from_coords().
        """
        if not emotion:
            return None
        for quadrant, emotions in EMOTION_GROUPS.items():
            if emotion.lower() in [e.lower() for e in emotions]:
                return quadrant
        return None

    def get_emotion_coordinates(self, emotion: str) -> Optional[Tuple[float, float]]:
        """
        Coordonnées de référence d'un label. N'intervient plus dans la mesure :
        les deux canaux produisent leur propre point continu. Conservé comme
        repli et pour nommer le point le plus proche.
        """
        return EMOTION_COORDINATES.get(emotion.lower(), None)

    def calculate_emotion_distance(self, emotion1: str, emotion2: str) -> Optional[float]:
        """
        Distance entre deux LABELS dans le plan valence-arousal.
        Référence : modèle circumplexe de Russell (1980). Repli uniquement.
        """
        coord1 = self.get_emotion_coordinates(emotion1)
        coord2 = self.get_emotion_coordinates(emotion2)
        if not coord1 or not coord2:
            return None
        return float(np.hypot(coord1[0] - coord2[0], coord1[1] - coord2[1]))

    # ------------------------------------------------------------------
    # Fusion
    # ------------------------------------------------------------------

    @staticmethod
    def _confidence_weight(
        score: float, floor: float = CONFIDENCE_FLOOR, ceil: float = CONFIDENCE_CEIL
    ) -> float:
        """
        Fiabilité brute d'un canal (0-100) -> poids de fusion (0-1). Sous le
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
        0 sous le seuil, montée linéaire jusqu'à 1 au seuil SEVERE.
        Remplace un déclenchement binaire par une gradation continue.
        """
        low = SEUIL_DISSONANCE_DISTANCE
        high = ALERT_SEVERE_DISTANCE
        if distance <= low:
            return 0.0
        if distance >= high:
            return 1.0
        return float((distance - low) / (high - low))

    def apply_cross_modal_check(
        self,
        face_emotion: Optional[str],
        face_score: float,
        face_coordinates: Optional[Tuple[float, float]],
        voice_coordinates: Optional[Tuple[float, float]],
    ) -> Tuple[Optional[str], float]:
        """
        Confronte la valence du visage à celle de la voix.

        DÉSACTIVÉ PAR DÉFAUT, et c'est délibéré. Ce mécanisme a été introduit
        pour compenser un défaut de FER, qui confondait happy et sad : quand la
        voix contredisait un label facial peu confiant, on supposait une erreur
        de classification. Depuis le passage à EmotiEffLib, le point facial ne
        dérive plus d'un label mais d'une régression, et ce raisonnement ne
        s'applique plus.

        Surtout, il est circulaire : il utilise le DÉSACCORD entre les deux
        canaux comme critère pour disqualifier l'un d'eux, alors que ce désaccord
        est précisément l'objet de la mesure. La fiabilité de chaque canal est
        désormais estimée à l'intérieur de ce canal — dispersion intra-fenêtre
        côté visage, concordance des sous-fenêtres côté voix — et jamais par
        comparaison avec l'autre.

        Conservé activable (FACE_VETO_MODE) pour pouvoir mesurer l'écart entre
        les deux comportements sur un même corpus.

        Returns: (face_emotion, face_score ajusté)
        """
        if FACE_VETO_MODE == "desactive":
            return face_emotion, face_score

        if not face_emotion or not face_coordinates or not voice_coordinates:
            return face_emotion, face_score

        if face_score >= FACE_VETO_MAX_CONFIDENCE:
            return face_emotion, face_score

        valence_visage = face_coordinates[0]
        valence_voix = voice_coordinates[0]

        contradicted = (
            (valence_visage > 0.05 and valence_voix < VOICE_NEG_THRESHOLD)
            or (valence_visage < -0.05 and valence_voix > VOICE_POS_THRESHOLD)
        )
        if not contradicted:
            return face_emotion, face_score

        if FACE_VETO_MODE == "rejet":
            logger.info(
                "Veto cross-modal (mode rejet) : valence visage %.2f contredite par "
                "valence voix %.2f -> fenêtre visage rejetée",
                valence_visage, valence_voix,
            )
            return None, 0.0

        # La pénalité porte sur la MARGE au-dessus du plancher d'exploitabilité,
        # pas sur le score brut : sinon toute pénalité ramènerait mécaniquement
        # sous le plancher, soit un rejet binaire déguisé.
        adjusted = float(
            CONFIDENCE_FLOOR + max(0.0, face_score - CONFIDENCE_FLOOR) * FACE_VETO_PENALTY
        )
        logger.info(
            "Pénalité cross-modale : valence visage %.2f contredite par valence voix "
            "%.2f -> fiabilité visage %.1f -> %.1f",
            valence_visage, valence_voix, face_score, adjusted,
        )
        return face_emotion, adjusted

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
          1. Les deux canaux fournissent leur point continu (valence, arousal).
          2. Distance euclidienne D entre ces deux points.
          3. Degré flou de D (au lieu d'un seuil binaire).
          4. Fusion pondérée par la fiabilité de chaque canal.

        Attention au vocabulaire : la valeur renvoyée sous le nom "confidence"
        n'est PAS une probabilité que la dissonance existe. C'est le produit de
        la fiabilité moyenne des deux canaux par le degré d'incongruence. Elle
        décrit la qualité de la mesure ET l'ampleur de l'écart, pas une
        vraisemblance clinique.

        Limite connue, à déclarer plutôt qu'à masquer : cette moyenne est
        pondérée, donc dominée par le canal le PLUS fiable. Or la fiabilité
        d'une comparaison est bornée par son maillon le plus faible. Une
        formulation en min(w_f, w_v) serait plus juste, mais elle déplacerait
        tous les seuils de gradation : le choix a été laissé ouvert, faute de
        corpus permettant de recalibrer.

        Returns: (is_dissonant, confidence, alert_level, emotion_distance)
        """
        if not face_emotion or not voice_emotion:
            return False, 0.0, "NONE", 0.0

        # Distance entre les deux points mesurés. Repli sur les coordonnées de
        # référence des labels si un point manque (ne devrait pas arriver : les
        # deux modèles produisent nativement un point continu).
        if face_coordinates and voice_coordinates:
            emotion_distance = float(
                np.hypot(
                    face_coordinates[0] - voice_coordinates[0],
                    face_coordinates[1] - voice_coordinates[1],
                )
            )
        else:
            emotion_distance = self.calculate_emotion_distance(face_emotion, voice_emotion) or 0.0

        fuzzy_mu = self._fuzzy_dissonance_membership(emotion_distance)

        w_f = self._confidence_weight(face_score)
        w_v = self._confidence_weight(voice_score)
        weight_sum = w_f + w_v
        # Une dissonance est une COMPARAISON entre deux canaux : si l'un des deux
        # est jugé inexploitable, l'écart mesuré entre les deux points ne veut
        # rien dire. Une condition portant sur la seule SOMME des poids laissait
        # passer des fenêtres où un unique canal portait toute la mesure.
        if w_f <= 0.0 or w_v <= 0.0 or weight_sum < 0.2:
            return False, 0.0, "NONE", emotion_distance

        confidence = float((w_f * face_score + w_v * voice_score) / weight_sum * fuzzy_mu)

        # fuzzy_mu=0 (sous le seuil de distance) donne confidence=0.
        is_dissonant = confidence > 0.0

        # Gradation par distance / confiance. Les seuils viennent de la
        # configuration : ce sont eux qu'il faut recalibrer sur un corpus de
        # référence, pas le code.
        alert_level = "NONE"
        if is_dissonant:
            if (emotion_distance >= ALERT_SEVERE_DISTANCE
                    or confidence >= ALERT_SEVERE_CONFIDENCE):
                alert_level = "SEVERE"
            elif (emotion_distance >= ALERT_MODERATE_DISTANCE
                    or confidence >= ALERT_MODERATE_CONFIDENCE):
                alert_level = "MODERATE"
            else:
                alert_level = "VIGILANCE"

        return is_dissonant, round(confidence, 1), alert_level, emotion_distance

    # ------------------------------------------------------------------
    # Calibration d'échelle inter-canaux
    # ------------------------------------------------------------------

    def get_calibration_stats(self) -> Dict[str, Any]:
        """
        Statistiques des points bruts observés sur les deux canaux.

        Sert à calibrer EMOTIEFFLIB_VA_GAIN sur des données réelles plutôt que
        de le fixer au jugé : le gain qui harmonise les deux échelles est le
        rapport des amplitudes observées. Aucune image ni aucun son n'est
        conservé, seulement des couples (valence, arousal) anonymes, en mémoire.
        """
        def describe(samples, gain=1.0):
            if not samples:
                return {"n": 0}
            arr = np.asarray(samples, dtype=np.float32) * gain
            mag = np.linalg.norm(arr, axis=1)
            return {
                "n": int(arr.shape[0]),
                "valence": {
                    "p5": round(float(np.percentile(arr[:, 0], 5)), 3),
                    "p50": round(float(np.percentile(arr[:, 0], 50)), 3),
                    "p95": round(float(np.percentile(arr[:, 0], 95)), 3),
                },
                "arousal": {
                    "p5": round(float(np.percentile(arr[:, 1], 5)), 3),
                    "p50": round(float(np.percentile(arr[:, 1], 50)), 3),
                    "p95": round(float(np.percentile(arr[:, 1], 95)), 3),
                },
                "magnitude_p95": round(float(np.percentile(mag, 95)), 3),
            }

        # Copies : ces deques sont alimentées depuis les threads d'inférence.
        calib_face = list(self._calib_face)
        calib_voice = list(self._calib_voice)
        face_raw = describe(calib_face)
        face_applique = describe(calib_face, EMOTIEFFLIB_VA_GAIN)
        voice = describe(calib_voice)

        suggested = None
        if face_raw.get("n", 0) >= 30 and voice.get("n", 0) >= 30:
            f95 = face_raw["magnitude_p95"]
            if f95 > 1e-6:
                suggested = round(voice["magnitude_p95"] / f95, 2)

        return {
            "gain_actuel": EMOTIEFFLIB_VA_GAIN,
            "gain_suggere": suggested,
            "commentaire": (
                "gain_suggere harmonise les amplitudes des deux canaux (rapport des "
                "magnitudes au 95e percentile). Au moins 30 fenêtres par canal sont "
                "nécessaires ; une session de calibration de plusieurs minutes sur un "
                "matériel représentatif est préférable."
            ),
            "visage_brut": face_raw,
            "visage_apres_gain": face_applique,
            "voix": voice,
        }


# Instance singleton du service d'émotions
emotion_service = EmotionService()
