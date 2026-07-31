"""
État d'une session d'analyse et décision par fenêtre.

Ce module contient TOUTE la logique de décision appliquée à une fenêtre : gestion
des ruptures de contexte, conditions de fusion, gradation, persistance et
cooldown de la vibration. La boucle temps réel (api.main) et le banc
d'évaluation hors ligne (tools.evaluate_corpus) l'utilisent tous les deux, ce
qui garantit que les mesures faites sur corpus portent bien sur le système
réellement exécuté en séance, et non sur une réimplémentation approchante.
"""
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from config.settings import (
    FACE_MAX_DISPERSION,
    FACE_MIN_SAMPLES,
    FACE_SMOOTH_WINDOW,
    VOICE_SMOOTH_WINDOW,
    NO_FACE_WINDOWS_BEFORE_RESET,
    PERSISTENCE_MIN,
    PERSISTENCE_WINDOW,
    SEUIL_MIN_VOIX,
    SILENCE_WINDOWS_BEFORE_RESET,
    VIBRATION_COOLDOWN_SECONDS,
    WARMUP_WINDOWS_AFTER_RESET,
)

logger = logging.getLogger(__name__)


@dataclass
class WindowOutcome:
    """Résultat complet d'une fenêtre d'analyse."""

    # Canal visuel
    face_emotion: Optional[str] = None
    face_score: float = 0.0
    face_coords: Optional[Tuple[float, float]] = None
    face_dispersion: Optional[float] = None
    n_face_samples: int = 0

    # Canal vocal
    voice_emotion: Optional[str] = None
    voice_score: float = 0.0
    voice_coords: Optional[Tuple[float, float]] = None
    voice_subwindows: int = 0

    # Fusion
    is_dissonant: bool = False
    confidence: float = 0.0
    alert_level: str = "NONE"
    emotion_distance: float = 0.0

    # Décisions
    should_vibrate: bool = False
    skipped: Optional[str] = None      # raison de non-évaluation, sinon None
    resets: List[str] = field(default_factory=list)

    @property
    def evaluated(self) -> bool:
        """Vrai si la fenêtre a été soumise au calcul de dissonance."""
        return self.skipped is None


class AnalysisSession:
    """
    Suit l'état d'une session : ruptures de contexte, fenêtres de reprise,
    persistance de l'alerte et cooldown de la vibration.
    """

    def __init__(self, emotion_service, clock=time.monotonic, warmup_windows=None):
        """
        warmup_windows : nombre de fenêtres ignorées après une purge. Par défaut
            WARMUP_WINDOWS_AFTER_RESET. L'évaluation hors ligne peut le mettre à
            zéro : elle instancie une session neuve par clip, donc aucune mémoire
            d'une scène précédente ne peut contaminer la première fenêtre — le
            garde-fou n'a rien à protéger et coûterait la totalité des mesures
            sur des extraits courts.
        """
        self._service = emotion_service
        self._clock = clock
        self._warmup = (
            WARMUP_WINDOWS_AFTER_RESET if warmup_windows is None else max(0, int(warmup_windows))
        )
        self.reset(purge_models=True, reason="démarrage de session")

    def reset(self, purge_models: bool = True, reason: str = "") -> None:
        """Repart d'un état vierge. À appeler entre deux séances ou deux clips."""
        self._recent_dissonant = deque(maxlen=PERSISTENCE_WINDOW)
        self._last_vibration_ts = -1e9
        self._silence_streak = 0
        self._no_face_streak = 0
        self._valid_windows = 0
        if purge_models:
            self._service.reset_state()
        if reason:
            logger.info("Session réinitialisée (%s).", reason)

    def _partial_reset(self, outcome: WindowOutcome, what: str, message: str) -> None:
        """
        Purge la mémoire d'un canal sans réinitialiser toute la session.

        L'historique d'alerte, lui, n'est effacé que si une mémoire
        INTER-fenêtres était réellement en jeu (lissage actif). Sans lissage,
        chaque fenêtre est déjà indépendante : remettre à zéro la persistance
        et le warm-up ne protégeait de rien et empêchait en pratique toute
        vibration, celle-ci exigeant plusieurs fenêtres dissonantes de suite.
        """
        if what == "voice":
            self._service.reset_voice_state()
        else:
            self._service.reset_face_state()
        if FACE_SMOOTH_WINDOW > 1 or VOICE_SMOOTH_WINDOW > 1:
            self._recent_dissonant.clear()
            self._valid_windows = 0
        outcome.resets.append(what)
        logger.info(message)

    def process_window(
        self,
        face_samples: List[Dict[str, Any]],
        audio_data,
        sample_rate: int,
    ) -> WindowOutcome:
        """
        Applique à une fenêtre la totalité de la chaîne de décision.

        face_samples : images analysées PENDANT la fenêtre audio (même intervalle).
        """
        out = WindowOutcome()

        (
            out.face_emotion,
            out.face_score,
            out.face_coords,
            out.face_dispersion,
            out.n_face_samples,
        ) = self._service.aggregate_face_window(face_samples)

        (
            out.voice_emotion,
            out.voice_score,
            out.voice_coords,
        ) = self._service.detect_audio_emotion(audio_data, sample_rate)
        out.voice_subwindows = getattr(self._service, "last_voice_subwindows", 0)

        # --- Ruptures de contexte ------------------------------------------
        # Sans purge, la mémoire d'un canal survit au changement de scène : le
        # premier visage d'une nouvelle séquence se retrouve comparé à la voix
        # de la séquence précédente.
        if out.voice_coords is None:
            self._silence_streak += 1
            if self._silence_streak == SILENCE_WINDOWS_BEFORE_RESET:
                self._partial_reset(
                    out, "voice",
                    "Aucun signal vocal sur %d fenêtre(s) : mémoire vocale purgée."
                    % self._silence_streak,
                )
        else:
            self._silence_streak = 0

        if out.n_face_samples < FACE_MIN_SAMPLES:
            self._no_face_streak += 1
            if self._no_face_streak == NO_FACE_WINDOWS_BEFORE_RESET:
                self._partial_reset(
                    out, "face",
                    "Visage exploitable sur %d image(s) seulement (minimum %d) : "
                    "mémoire faciale purgée." % (out.n_face_samples, FACE_MIN_SAMPLES),
                )
        else:
            self._no_face_streak = 0

        # Confrontation cross-modale (désactivée par défaut).
        out.face_emotion, out.face_score = self._service.apply_cross_modal_check(
            out.face_emotion, out.face_score, out.face_coords, out.voice_coords
        )

        # --- Conditions de fusion ------------------------------------------
        if (
            out.face_emotion is None
            or out.face_coords is None
            or out.n_face_samples < FACE_MIN_SAMPLES
        ):
            out.skipped = "visage"
        elif (
            out.voice_emotion is None
            or out.voice_coords is None
            or out.voice_score <= SEUIL_MIN_VOIX
        ):
            out.skipped = "voix"
        elif out.face_dispersion is None or out.face_dispersion > FACE_MAX_DISPERSION:
            # Le visage a trop varié dans la fenêtre : aucun point ne le résume,
            # la comparaison avec la voix n'a pas de sens.
            out.skipped = "visage instable"
            logger.info(
                "Fenêtre écartée : visage trop instable (dispersion=%.2f > %.2f).",
                out.face_dispersion, FACE_MAX_DISPERSION,
            )
        else:
            self._valid_windows += 1
            if self._valid_windows <= self._warmup:
                out.skipped = "reprise"
                logger.info(
                    "Fenêtre de reprise ignorée (%d/%d) : les deux canaux viennent "
                    "de redémarrer sur une nouvelle scène.",
                    self._valid_windows, self._warmup + 1,
                )
            else:
                (
                    out.is_dissonant,
                    out.confidence,
                    out.alert_level,
                    out.emotion_distance,
                ) = self._service.detect_dissonance(
                    out.face_emotion, out.face_score,
                    out.voice_emotion, out.voice_score,
                    out.voice_coords, out.face_coords,
                )

        # --- Persistance et cooldown ---------------------------------------
        self._recent_dissonant.append(1 if out.is_dissonant else 0)

        if out.is_dissonant and out.alert_level in ("MODERATE", "SEVERE"):
            confirmed = sum(self._recent_dissonant) >= PERSISTENCE_MIN
            now = self._clock()
            if confirmed and now - self._last_vibration_ts >= VIBRATION_COOLDOWN_SECONDS:
                out.should_vibrate = True
                self._last_vibration_ts = now
            elif not confirmed:
                logger.info(
                    "Vibration différée : dissonance non confirmée (%d/%d fenêtres)",
                    sum(self._recent_dissonant), PERSISTENCE_MIN,
                )

        return out
