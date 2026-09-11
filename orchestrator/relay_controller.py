#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Driver Relè Modbus TCP (Waveshare)

Caratteristiche:
- Comunica con la scheda relè Waveshare Modbus TCP to RTU su IP 192.168.1.30, porta 4196.
- Gestione Intelligente dei Timer (Watchdog / Anti-sfarfallio):
  Se arrivano eventi rapidi consecutivi mentre un faretto è già acceso, il relè non scatta
  a raffica né subisce spegnimenti anticipati: la scadenza viene automaticamente prolungata.
- Supporto multicanale dinamico per fari indipendenti per ciascuna telecamera/varco.
- Canale 2 (Indirizzo Modbus 1): Predisposto per impulso Cancello (3s).
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
        
        # Strutture per la gestione intelligente dei timer (canale -> timestamp scadenza)
        self._active_expirations = {}
        self._active_threads = {}

    def _get_client(self):
        return ModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout)

    def set_relay(self, channel: int, state: bool) -> bool:
        """
        Imposta lo stato di un canale relè (0-based: 0 = Canale 1, 1 = Canale 2, ecc.).
        state: True = Acceso (chiuso), False = Spento (aperto).
        """
        with self._lock:
            client = self._get_client()
            try:
                if not client.connect():
                    logger.error("Impossibile connettersi alla scheda relè %s:%d", self.host, self.port)
                    return False
                
                # Scrittura del singolo coil (funzione Modbus 0x05)
                res = client.write_coil(address=channel, value=state)
                if res.isError():
                    logger.error("Errore scrittura relè canale %d (stato: %s): %s", channel + 1, state, res)
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
        Attiva il relè e lo spegne automaticamente dopo 'duration_seconds'.
        Se il canale è GIÀ attivo (es. persona che continua a muoversi o eventi ravvicinati),
        il timer viene semplicemente esteso senza spegnere o far scattare il relè.
        """
        with self._lock:
            new_expiration = time.time() + duration_seconds
            
            # Se esiste già un thread attivo per questo canale, prolunghiamo semplicemente la scadenza
            if channel in self._active_threads and self._active_threads[channel].is_alive():
                current_exp = self._active_expirations.get(channel, time.time())
                self._active_expirations[channel] = max(current_exp, new_expiration)
                remaining = self._active_expirations[channel] - time.time()
                logger.info("Prolungato timer relè Canale %d (rimangono %.1fs)", channel + 1, remaining)
                return

            # Altrimenti registriamo la nuova scadenza e avviamo il worker dedicato
            self._active_expirations[channel] = new_expiration

        def _smart_pulse_worker():
            # Accende il relè
            success = self.set_relay(channel, True)
            if not success:
                with self._lock:
                    self._active_expirations.pop(channel, None)
                    self._active_threads.pop(channel, None)
                return

            logger.info("Relè Canale %d acceso per impulso (durata iniziale: %.1fs)", channel + 1, duration_seconds)

            # Loop di attesa intelligente: controlla se la scadenza è stata prolungata
            while True:
                time.sleep(0.5)
                with self._lock:
                    exp_time = self._active_expirations.get(channel, 0.0)
                    now = time.time()
                    if now >= exp_time:
                        break

            # Spegnimento pulito a scadenza definitiva completata
            self.set_relay(channel, False)
            with self._lock:
                self._active_expirations.pop(channel, None)
                self._active_threads.pop(channel, None)
            logger.info("Fine temporizzazione relè Canale %d (SPENTO)", channel + 1)

        t = threading.Thread(target=_smart_pulse_worker, daemon=True)
        with self._lock:
            self._active_threads[channel] = t
        t.start()

    # Comandi ad alto livello specifici per Sentinel AI
    def accendi_faretto(self, channel: int = 0, durata_secondi: float = 30.0):
        """Attiva il Faretto sul canale specificato (default canale 0 / Canale 1) per il tempo stabilito."""
        self.trigger_pulse(channel=channel, duration_seconds=durata_secondi)

    def apri_cancello(self, channel: int = 1, impulso_secondi: float = 3.0):
        """Dà un impulso sul Canale 2 (indirizzo 1) per aprire il cancello."""
        self.trigger_pulse(channel=channel, duration_seconds=impulso_secondi)

