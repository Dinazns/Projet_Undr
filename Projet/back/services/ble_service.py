"""
Service de communication BLE avec la montre Blackview R50.
Gère la connexion, l'envoi de notifications et les vibrations.
"""
import asyncio
import logging
import time
from typing import Any, Optional

# bleak est importé à la connexion, pas au chargement du module : le backend
# doit pouvoir démarrer et analyser sur une machine sans pile Bluetooth, et le
# banc d'évaluation hors ligne n'a aucun besoin de cette dépendance.

from config.settings import (
    MAC_MONTRE,
    FEE2_UUID,
    NOTIF_CALL,
    NOTIF_CALL_OFF_HOOK,
    VIBRATION_DURATION_SECONDS,
)

# Configuration du logging
logger = logging.getLogger(__name__)


class BLEService:
    _instance: Optional['BLEService'] = None
    _client: Optional[Any] = None
    _connected: bool = False
    # Durée du dernier write GATT, en millisecondes. C'est la seule latence
    # réellement imputable au lien Bluetooth ; exposée par /health pour pouvoir
    # la mesurer au lieu de l'estimer.
    last_write_latency_ms: Optional[float] = None
    # Référence sur la tâche de raccrochage. Sans elle, asyncio ne garde qu'une
    # référence faible sur les tâches créées par create_task : le ramasse-miettes
    # peut les collecter avant leur terme et la vibration reste active.
    _release_task = None

    def __new__(cls):
        """Singleton pour garantir une seule instance du service BLE"""
        if cls._instance is None:
            cls._instance = super(BLEService, cls).__new__(cls)
        return cls._instance

    @staticmethod
    def _make_packet(cmd: int, payload: bytes = b"") -> bytes:
        """
        Construit un paquet Moyoung.
        
        Format: FE EA 10 <total_len> <cmd> <payload>
        """
        total_len = 5 + len(payload)
        packet = bytearray(total_len)
        packet[0] = 0xFE
        packet[1] = 0xEA
        packet[2] = 0x10
        packet[3] = total_len & 0xFF
        packet[4] = cmd & 0xFF
        if payload:
            packet[5:] = payload
        return bytes(packet)

    async def connect(self, sync_time: bool = False) -> bool:
        """
        Se connecte à la montre.
        
        Args:
            sync_time: Si True, synchronise l'heure de la montre (défaut: False)
        """
        try:
            from bleak import BleakClient
        except ImportError:
            logger.error(
                "bleak n'est pas installé : la montre est indisponible. "
                "L'analyse continue, seule l'alerte haptique est désactivée."
            )
            self._connected = False
            return False

        try:
            logger.info(f"Tentative de connexion à la montre {MAC_MONTRE}...")
            self._client = BleakClient(MAC_MONTRE)
            await self._client.connect()
            self._connected = True
            logger.info("Montre connectée !")

            # Synchroniser l'heure seulement si demandé
            if sync_time:
                await self._sync_time()
            return True
        except Exception as e:
            logger.error(f"Erreur de connexion BLE: {e}")
            self._connected = False
            return False

    async def _sync_time(self) -> None:
        """Synchronise l'heure de la montre"""
        if not self._connected or not self._client:
            logger.warning("Impossible de synchroniser l'heure: pas connecté")
            return
        
        try:
            # La montre attend une heure locale. L'ancienne valeur ajoutait
            # 8 heures en dur (UTC+8, héritage du protocole Moyoung d'origine) :
            # l'heure affichée était fausse partout ailleurs. On calcule ici le
            # décalage local réel, DST comprise.
            now = time.time()
            utc_offset = -(time.altzone if time.localtime(now).tm_isdst else time.timezone)
            ts = int(now) + utc_offset
            payload = bytes([
                (ts >> 24) & 0xFF,
                (ts >> 16) & 0xFF,
                (ts >> 8) & 0xFF,
                ts & 0xFF,
                0x08
            ])
            await self._send_moyoung(0x31, payload)
            logger.info("Heure synchronisée avec la montre")
        except Exception as e:
            logger.error(f"Erreur de synchronisation de l'heure: {e}")

    async def _send_moyoung(self, cmd: int, payload: bytes = b"") -> None:
        """Envoie un paquet Moyoung à la montre"""
        if not self._connected or not self._client:
            logger.warning("Pas connecté à la montre")
            return
        
        try:
            packet = self._make_packet(cmd, payload)
            hex_packet = " ".join(f"{b:02X}" for b in packet)
            logger.debug(f"Envoi paquet BLE: {hex_packet}")
            await self._client.write_gatt_char(FEE2_UUID, packet, response=False)
        except Exception as e:
            logger.error(f"Erreur d'envoi BLE: {e}")

    async def vibrate(self) -> None:
        """
        Déclenche la vibration : notification d'appel entrant, puis raccrochage
        après VIBRATION_DURATION_SECONDS.

        Le raccrochage part en tâche de fond. L'ancienne implémentation attendait
        la seconde complète avant de rendre la main : elle bloquait la boucle
        d'analyse, et surtout elle faisait passer la temporisation du motif pour
        de la latence de transmission. La latence réellement imputable au lien
        BLE est celle du premier write GATT, mesurée ci-dessous.
        """
        if not self._connected:
            logger.warning("Impossible de faire vibrer: pas connecté à la montre")
            return

        try:
            t0 = time.perf_counter()
            # 1. Simuler un appel entrant (déclenche la vibration).
            await self._send_moyoung(0x41, bytes([NOTIF_CALL]))
            latency_ms = (time.perf_counter() - t0) * 1000.0
            BLEService.last_write_latency_ms = latency_ms
            logger.info(
                "Vibration déclenchée | write GATT : %.1f ms (latence BLE mesurée)",
                latency_ms,
            )
            # 2. Raccrochage différé, hors du chemin critique.
            task = asyncio.create_task(self._release_call())
            BLEService._release_task = task
            task.add_done_callback(
                lambda t: setattr(BLEService, "_release_task", None)
            )
        except Exception as e:
            logger.error(f"Erreur lors de la vibration: {e}")

    async def _release_call(self) -> None:
        """Raccroche l'appel simulé une fois le motif de vibration terminé."""
        try:
            await asyncio.sleep(VIBRATION_DURATION_SECONDS)
            await self._send_moyoung(0x41, bytes([NOTIF_CALL_OFF_HOOK]))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Erreur lors du raccrochage de la vibration: {e}")

    async def disconnect(self) -> None:
        """Déconnecte proprement la montre"""
        if self._connected and self._client:
            try:
                await self._client.disconnect()
                self._connected = False
                logger.info("Montre déconnectée")
            except Exception as e:
                logger.error(f"Erreur de déconnexion BLE: {e}")

    @property
    def is_connected(self) -> bool:
        return self._connected


# Instance singleton du service BLE
ble_service = BLEService()
