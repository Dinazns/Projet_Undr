"""
Service de communication BLE avec la montre Blackview R50.
Gère la connexion, l'envoi de notifications et les vibrations.
"""
import asyncio
import logging
import time
from typing import Optional
from bleak import BleakClient

from config.settings import MAC_MONTRE, FEE2_UUID, NOTIF_CALL, NOTIF_CALL_OFF_HOOK

# Configuration du logging
logger = logging.getLogger(__name__)


class BLEService:
    _instance: Optional['BLEService'] = None
    _client: Optional[BleakClient] = None
    _connected: bool = False

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
            ts = int(time.time()) + 8 * 3600
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
        Fait vibrer la montre en simulant un appel entrant puis un raccrochage.
        """
        if not self._connected:
            logger.warning("Impossible de faire vibrer: pas connecté à la montre")
            return
        
        try:
            logger.info("Envoi vibration à la montre...")
            # 1. Simuler un appel entrant
            await self._send_moyoung(0x41, bytes([NOTIF_CALL]))
            # 2. Attendre 1 seconde
            await asyncio.sleep(1.0)
            # 3. Raccrocher
            await self._send_moyoung(0x41, bytes([NOTIF_CALL_OFF_HOOK]))
            logger.info("Vibration envoyée avec succès !")
        except Exception as e:
            logger.error(f"Erreur lors de la vibration: {e}")

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
