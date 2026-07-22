"""
Utilitaire de capture d'écran pour le HUD.
"""
import io
import base64
import logging
from typing import Optional, Dict
from mss import mss
from PIL import Image

logger = logging.getLogger(__name__)


class ScreenCapture:
    def __init__(self):
        self._hud_coords: Dict[str, int] = {"x": 0, "y": 0, "w": 0, "h": 0}
        self._sct = mss()

    def set_hud_coords(self, x: int, y: int, w: int, h: int) -> None:
        """
        Met à jour les coordonnées du HUD à capturer.
        """
        self._hud_coords = {"x": x, "y": y, "w": w, "h": h}
        logger.debug(f"Coordonnées HUD mises à jour: {self._hud_coords}")

    def clear_hud_coords(self) -> None:
        """
        Réinitialise la zone de capture quand la session HUD est terminée.
        """
        self._hud_coords = {"x": 0, "y": 0, "w": 0, "h": 0}
        logger.info("Coordonnées HUD réinitialisées")

    def capture_hud(self) -> Optional[str]:
        """
        Capture la zone du HUD et retourne l'image encodée en base64.
        
        Returns: Image en base64 ou None si capture impossible
        """
        if self._hud_coords["w"] <= 0 or self._hud_coords["h"] <= 0:
            return None

        try:
            monitor = {
                "top": self._hud_coords["y"],
                "left": self._hud_coords["x"],
                "width": self._hud_coords["w"],
                "height": self._hud_coords["h"],
            }
            screenshot = self._sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            # 448 px / qualité 80 : crop de visage plus net pour FER. Le CPU
            # suit largement, la boucle étant cadencée par l'audio.
            img.thumbnail((448, 448))

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            logger.error(f"Erreur de capture d'écran: {e}")
            return None
