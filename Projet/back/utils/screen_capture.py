"""
Capture de la zone d'écran du HUD.
"""
import logging
from typing import Dict, Optional

import cv2
import numpy as np
from mss import mss

from config.settings import CAPTURE_MAX_SIZE

logger = logging.getLogger(__name__)

# Nombre d'échecs consécutifs avant de recréer l'objet mss. Un changement de
# résolution, un verrouillage de session ou un basculement d'écran invalide le
# handle sans qu'aucune exception ne le signale ensuite : sans réinitialisation,
# la capture reste morte jusqu'au redémarrage du backend.
_MAX_FAILURES_BEFORE_RESET = 5


class ScreenCapture:
    def __init__(self):
        self._hud_coords: Dict[str, int] = {"x": 0, "y": 0, "w": 0, "h": 0}
        self._sct = None
        self._failures = 0
        self._ensure_backend()

    def _ensure_backend(self) -> None:
        if self._sct is None:
            self._sct = mss()
            logger.debug("Backend de capture (mss) initialisé")

    def set_hud_coords(self, x: int, y: int, w: int, h: int) -> None:
        """Met à jour les coordonnées de la zone à capturer."""
        self._hud_coords = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
        logger.debug("Coordonnées HUD mises à jour: %s", self._hud_coords)

    def clear_hud_coords(self) -> None:
        """Réinitialise la zone de capture quand la session HUD est terminée."""
        self._hud_coords = {"x": 0, "y": 0, "w": 0, "h": 0}
        logger.info("Coordonnées HUD réinitialisées")

    def capture_hud_array(self) -> Optional[np.ndarray]:
        """
        Capture la zone du HUD et renvoie une image BGR (ndarray).

        Aucun encodage intermédiaire. La version précédente encodait en JPEG
        (qualité 80) puis en base64, pour décoder immédiatement après dans le
        même processus : ce cycle coûtait du temps CPU à chaque image et
        ajoutait une TROISIÈME compression au signal, après celle de la
        visioconférence et celle du rendu écran, sur le flux même dont on
        cherche à analyser les détails fins.

        Returns: image BGR, ou None si la capture est impossible.
        """
        if self._hud_coords["w"] <= 0 or self._hud_coords["h"] <= 0:
            return None

        try:
            self._ensure_backend()
            monitor = {
                "top": self._hud_coords["y"],
                "left": self._hud_coords["x"],
                "width": self._hud_coords["w"],
                "height": self._hud_coords["h"],
            }
            screenshot = self._sct.grab(monitor)

            # mss renvoie du BGRA : on retire le canal alpha sans recopie inutile.
            frame = np.asarray(screenshot, dtype=np.uint8)[:, :, :3]

            # Réduction seulement si nécessaire, en INTER_AREA (le filtre adapté
            # à la décimation, contrairement au filtre par défaut).
            h, w = frame.shape[:2]
            longest = max(h, w)
            if longest > CAPTURE_MAX_SIZE:
                scale = CAPTURE_MAX_SIZE / float(longest)
                frame = cv2.resize(
                    frame,
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    interpolation=cv2.INTER_AREA,
                )

            self._failures = 0
            # np.asarray sur un ScreenShot renvoie une vue en lecture seule sur
            # le buffer de mss, réécrit à la capture suivante : on copie.
            return np.ascontiguousarray(frame)

        except Exception as e:
            self._failures += 1
            logger.error(
                "Erreur de capture d'écran (%d échec(s) consécutif(s)): %s",
                self._failures, e,
            )
            if self._failures >= _MAX_FAILURES_BEFORE_RESET:
                logger.warning(
                    "Réinitialisation du backend de capture après %d échecs.",
                    self._failures,
                )
                try:
                    if self._sct is not None:
                        self._sct.close()
                except Exception:
                    pass
                self._sct = None
                self._failures = 0
            return None
