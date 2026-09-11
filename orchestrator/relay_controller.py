#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Driver Relè Modbus TCP (Waveshare)

Caratteristiche:
- Comunica con la scheda relè Waveshare Modbus TCP to RTU su IP 192.168.1.30, porta 4196.
- Canale 1 (Indirizzo Modbus 0): Collegato al Faretto / Illuminazione dissuasione.
- Canale 2 (Indirizzo Modbus 1): Predisposto per Cancello / Sirena aggiuntiva.
- Supporta comandi ON, OFF e IMPULSO temporizzato (es. accendi per N secondi e poi spegni automaticamente).
- Gestione robusta di timeout e disconnessioni (non blocca mai l'orchestratore).
"""

import time
import logging
import threading
from pymodbus.client import ModbusTcpClient

logger = logging.getLogger("SentinelRelay")

class WaveshareRelayController:
    def __init__(self, host="192.168.1.30", port=4196, timeout=3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._lock = threading.Lock()

    def _get_client(self):
        return ModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout)

    def set_relay(self, channel: int, state: bool) -> bool:
        """
        Imposta lo stato di un canale relè (0-based: 0 = Canale 1, 1 = Canale 2).
        state: True = Acceso (chiuso), False = Spento (aperto).
        """
        with self._lock:
            client = self._get_client()
            try:
                if not client.connect():
                    logger.error("Impossibile connettersi alla scheda relè %s:%d", self.host, self.port)
                    return False
                
                # Scrittura del singolo coil (funzione Modbus 0x05)
                # Waveshare: indirizzo 0 = Relè 1, 1 = Relè 2
                res = client.write_coil(address=channel, value=state)
                if res.isError():
                    logger.error("Errore scrittura relè canale %d (stato: %s): %s", channel, state, res)
                    return False
                
                logger.info("Relè Canale %d impostato su %s", channel + 1, "ACCESO" if state else "SPENTO")
                return True
            except Exception as exc:
                logger.error("Eccezione durante il comando relè %s:%d: %s", self.host, self.port, exc)
                return False
            finally:
                client.close()

    def trigger_pulse(self, channel: int, duration_seconds: float = 30.0):
        """
        Accende il relè e lo spegne automaticamente dopo 'duration_seconds' in un thread separato.
        Ideale per accensione faretto temporizzato o impulso cancello.
        """
        def _pulse_worker():
            logger.info("Avvio impulso relè Canale %d per %.1f secondi", channel + 1, duration_seconds)
            if self.set_relay(channel, True):
                time.sleep(duration_seconds)
                self.set_relay(channel, False)
                logger.info("Fine impulso relè Canale %d (ripristinato a SPENTO)", channel + 1)

        t = threading.Thread(target=_pulse_worker, daemon=True)
        t.start()

    # Comandi ad alto livello specifici per Sentinel AI
    def accendi_faretto(self, durata_secondi: float = 30.0):
        """Attiva il Faretto sul Canale 1 (indirizzo 0) per il tempo stabilito."""
        self.trigger_pulse(channel=0, duration_seconds=durata_secondi)

    def apri_cancello(self, impulso_secondi: float = 3.0):
        """Dà un impulso di 3 secondi sul Canale 2 (indirizzo 1) per aprire il cancello."""
        self.trigger_pulse(channel=1, duration_seconds=impulso_secondi)
