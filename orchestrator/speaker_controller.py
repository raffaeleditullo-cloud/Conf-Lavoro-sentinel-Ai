#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Driver Altoparlante IP (Fanvil A233)

Caratteristiche:
- Comunica con l'altoparlante Fanvil su IP 192.168.1.31.
- Supporta la riproduzione remota via API HTTP / CGI standard Fanvil:
  `http://<IP>/cgi-bin/ConfigManApp.com?key=...` oppure streaming audio multicast / SIP.
- Supporta anche la riproduzione in locale / streaming verso l'altoparlante tramite URL diretto.
- Thread-safe: non interrompe o rallenta il ciclo principale dell'orchestratore se l'altoparlante impiega tempo a rispondere.
"""

import os
import logging
import threading
import requests

logger = logging.getLogger("SentinelSpeaker")

class FanvilSpeakerController:
    def __init__(self, host="192.168.1.31", http_port=80, user="admin", password="admin", timeout=4.0):
        self.host = host
        self.http_port = http_port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.base_url = f"http://{self.host}:{self.http_port}"
        self._lock = threading.Lock()

    def play_audio_file(self, audio_filepath: str):
        """
        Invia il comando di riproduzione per il file specificato verso l'altoparlante Fanvil.
        Esegue la richiesta in background senza bloccare il flusso del rilevamento.
        """
        def _play_worker():
            if not os.path.exists(audio_filepath):
                logger.error("File audio non trovato: %s", audio_filepath)
                return

            filename = os.path.basename(audio_filepath)
            logger.info("Avvio riproduzione audio su Fanvil %s: %s", self.host, filename)

            # Fanvil API standard per avvio riproduzione audio o trigger allarme
            # NOTA: I dispositivi Fanvil supportano chiamate Action URL / CGI standard:
            # es. /cgi-bin/ConfigManApp.com?key=tone:alert o riproduzione via web server locale.
            try:
                # Esempio comando API Fanvil HTTP Digest/Basic Auth
                # Se l'altoparlante ha il file caricato a bordo o streaming:
                play_url = f"{self.base_url}/cgi-bin/ConfigManApp.com"
                params = {
                    "key": f"play:{filename}"
                }
                
                # Tentativo chiamata HTTP (con fallback morbido se siamo in modalità simulatore/collaudo)
                res = requests.get(
                    play_url,
                    params=params,
                    auth=(self.user, self.password),
                    timeout=self.timeout
                )
                if res.status_code == 200:
                    logger.info("Comando audio ricevuto con successo da Fanvil %s", self.host)
                else:
                    logger.warning("Fanvil %s ha risposto con codice HTTP %d", self.host, res.status_code)

            except requests.exceptions.RequestException as req_err:
                logger.warning(
                    "Altoparlante Fanvil %s non raggiungibile (%s). Se l'altoparlante non è ancora connesso al banco, questo è normale.",
                    self.host, req_err
                )
            except Exception as exc:
                logger.error("Errore imprevisto comando altoparlante: %s", exc)

        t = threading.Thread(target=_play_worker, daemon=True)
        t.start()
