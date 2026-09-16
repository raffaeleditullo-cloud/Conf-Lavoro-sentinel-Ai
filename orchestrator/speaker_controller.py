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
            abs_path = os.path.abspath(audio_filepath)

            if not os.path.exists(abs_path):
                logger.error(
                    "DISSUASIONE VOCALE NON ESEGUITA: file audio inesistente '%s'. "
                    "Verificare il montaggio della cartella audio nel container.",
                    abs_path
                )
                return

            try:
                size_bytes = os.path.getsize(abs_path)
            except OSError as size_err:
                logger.error("Impossibile leggere il file audio '%s': %s", abs_path, size_err)
                return

            if size_bytes == 0:
                logger.error("DISSUASIONE VOCALE NON ESEGUITA: file audio vuoto (0 byte): '%s'", abs_path)
                return

            filename = os.path.basename(abs_path)

            # ATTENZIONE — API DA VALIDARE SUL DISPOSITIVO REALE:
            # questo endpoint CGI e' una ipotesi di lavoro, non una specifica verificata
            # del firmware Fanvil A233. Inoltre invia il solo NOME del file, quindi
            # presuppone che l'MP3 sia gia' caricato a bordo dell'altoparlante: nessuna
            # procedura del progetto carica oggi quei file sul dispositivo.
            # Da confermare in campo con la documentazione del firmware installato.
            play_url = f"{self.base_url}/cgi-bin/ConfigManApp.com"
            params = {"key": f"play:{filename}"}

            logger.info(
                "Comando dissuasione vocale -> Fanvil %s:%d | file locale: '%s' (%d byte) | URL: %s?key=%s",
                self.host, self.http_port, abs_path, size_bytes, play_url, params["key"]
            )

            try:
                res = requests.get(
                    play_url,
                    params=params,
                    auth=(self.user, self.password),
                    timeout=self.timeout
                )
                if res.status_code == 200:
                    logger.info(
                        "Fanvil %s ha accettato il comando (HTTP 200) per '%s'. "
                        "Se non si sente audio, il file non e' presente a bordo del dispositivo "
                        "oppure l'endpoint CGI non e' quello corretto per questo firmware.",
                        self.host, filename
                    )
                elif res.status_code in (401, 403):
                    logger.error(
                        "DISSUASIONE VOCALE RIFIUTATA: Fanvil %s ha risposto HTTP %d (autenticazione). "
                        "Verificare SPEAKER_USER e SPEAKER_PASSWORD nel file .env.",
                        self.host, res.status_code
                    )
                else:
                    logger.error(
                        "DISSUASIONE VOCALE FALLITA: Fanvil %s ha risposto HTTP %d per '%s'. Corpo: %s",
                        self.host, res.status_code, filename, res.text[:200].replace("\n", " ")
                    )

            except requests.exceptions.ConnectTimeout:
                logger.error(
                    "DISSUASIONE VOCALE FALLITA: timeout di connessione (%.1fs) verso l'altoparlante "
                    "Fanvil %s:%d. Dispositivo spento, IP errato o non raggiungibile dalla rete del container.",
                    self.timeout, self.host, self.http_port
                )
            except requests.exceptions.ConnectionError as conn_err:
                logger.error(
                    "DISSUASIONE VOCALE FALLITA: altoparlante Fanvil %s:%d non raggiungibile (%s). "
                    "Verificare alimentazione, cablaggio e la variabile SPEAKER_HOST nel file .env.",
                    self.host, self.http_port, conn_err
                )
            except requests.exceptions.RequestException as req_err:
                logger.error(
                    "DISSUASIONE VOCALE FALLITA: errore HTTP verso Fanvil %s:%d (%s)",
                    self.host, self.http_port, req_err
                )
            except Exception as exc:
                logger.exception("Errore imprevisto nel comando altoparlante Fanvil %s: %s", self.host, exc)

        t = threading.Thread(target=_play_worker, daemon=True)
        t.start()
