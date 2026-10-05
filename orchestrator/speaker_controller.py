#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Driver Altoparlante IP (Fanvil A233)

MECCANISMO DI RIPRODUZIONE — MULTICAST RTP (collaudato in campo da Alessio)
--------------------------------------------------------------------------
L'A233 e' gia' configurato a bordo per ascoltare un canale MULTICAST RTP:
l'audio si invia come flusso RTP G.711 mu-law verso 239.255.1.1:5004 e lo
speaker lo diffonde immediatamente, senza alcuna chiamata SIP ne' HTTP.

Il comando di riferimento validato sul dispositivo reale resta utile per la
diagnosi in campo:

    ffmpeg -re -i <file.mp3> -af volume=<vol_float> -ac 1 -ar 8000
           -acodec pcm_mulaw -payload_type 0 -f rtp rtp://239.255.1.1:5004

ARCHITETTURA ATTUALE
La trasmissione non avvia piu' un processo ffmpeg per ogni annuncio: l'audio
viene consegnato all'AudioBus (rtp_audio_bus.py), unico proprietario del canale,
che invia direttamente i pacchetti RTP con lo stesso formato del comando sopra.
Le tracce MP3 vengono decodificate in mu-law una sola volta all'avvio e restano
in RAM (ulaw_audio.py): al momento dell'allarme la riproduzione e' immediata.

NOTA STORICA: la precedente implementazione usava l'endpoint HTTP
`/cgi-bin/ConfigManApp.com?key=play:<file>`. Quell'endpoint NON fa parte
dell'API reale del firmware A233: rispondeva HTTP 200 ma non riproduceva
nulla. E' stato rimosso per non lasciare in campo un falso positivo.

REQUISITI OPERATIVI
- `ffmpeg` resta necessario nel container solo per decodificare gli MP3 storici
  all'avvio (i file .ulaw non ne hanno bisogno).
- Il container deve avere `network_mode: host` in docker-compose.yml, altrimenti
  i pacchetti multicast restano confinati nel bridge Docker e non raggiungono
  l'interfaccia fisica su cui e' attestato il Fanvil.
- Sullo speaker vanno disattivati "Multicast Tone" e "Auto HangUp Tone",
  altrimenti al termine di ogni annuncio si sentono 3 bip (nota di Alessio).
"""

import os
import logging

from rtp_audio_bus import Priority, get_audio_bus
from ulaw_audio import audio_library

logger = logging.getLogger("SentinelSpeaker")

# Parametri del canale multicast, sovrascrivibili da variabili d'ambiente.
DEFAULT_MULTICAST_IP = os.environ.get("FANVIL_MULTICAST_IP", "239.255.1.1")
DEFAULT_MULTICAST_PORT = int(os.environ.get("FANVIL_MULTICAST_PORT", "5004"))

# Volume di riproduzione predefinito in percentuale (0-100) quando il chiamante
# non ne passa uno.
DEFAULT_VOLUME_PERCENT = float(os.environ.get("FANVIL_DEFAULT_VOLUME", "70"))


class FanvilSpeakerController:
    """
    Driver di riproduzione vocale verso l'altoparlante Fanvil A233 via Multicast RTP.

    I parametri `host`, `http_port`, `user` e `password` sono conservati per
    compatibilita' con i chiamanti esistenti e per la sola diagnostica
    (raggiungibilita' del dispositivo): il percorso audio NON li usa.
    """

    def __init__(
        self,
        host="192.168.1.31",
        http_port=80,
        user="admin",
        password="admin",
        timeout=4.0,
        multicast_ip=None,
        multicast_port=None,
        default_volume_percent=None,
    ):
        self.host = host
        self.http_port = http_port
        self.user = user
        self.password = password
        self.timeout = timeout

        self.multicast_ip = multicast_ip or DEFAULT_MULTICAST_IP
        self.multicast_port = int(multicast_port or DEFAULT_MULTICAST_PORT)
        self.default_volume_percent = (
            DEFAULT_VOLUME_PERCENT if default_volume_percent is None else float(default_volume_percent)
        )

        self.bus = get_audio_bus(self.multicast_ip, self.multicast_port)

        # Decodifica in background tutte le tracce note: il primo allarme non attende ffmpeg.
        audio_library.preload_async([
            os.environ.get("AUDIO_DIR", "/app/audio"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio"),
        ])

        logger.info(
            "Driver Fanvil A233 in modalita' MULTICAST RTP via AudioBus -> rtp://%s:%d "
            "(G.711 mu-law, 8 kHz mono, volume predefinito %.0f%%)",
            self.multicast_ip, self.multicast_port, self.default_volume_percent
        )

    # ──────────────────────────────────────────────────────────────────────
    # API pubblica
    # ──────────────────────────────────────────────────────────────────────
    def is_playing(self) -> bool:
        """True se un annuncio e' attualmente in riproduzione o in coda."""
        return self.bus.is_playing()

    def stop(self):
        """Termina immediatamente l'annuncio in corso e svuota la coda."""
        self.bus.stop()

    def play_audio_file(self, audio_filepath: str, volume_percent=None, priority=Priority.ALARM, queue=False):
        """
        Diffonde la traccia indicata (MP3, WAV o .ulaw) sull'altoparlante Fanvil.

        Non blocca il chiamante. Con il canale occupato da un annuncio di priorita'
        uguale o superiore la richiesta viene scartata (salvo queue=True); una
        priorita' superiore interrompe l'annuncio in corso.

        volume_percent: volume 0-100; se None usa FANVIL_DEFAULT_VOLUME (70).
        Restituisce True se la riproduzione e' stata accettata, False se scartata.
        """
        abs_path = os.path.abspath(audio_filepath)
        if not self._validate_file(abs_path):
            return False

        audio = audio_library.get(abs_path)
        if not audio:
            logger.error("DISSUASIONE VOCALE NON ESEGUITA: impossibile decodificare '%s'.", abs_path)
            return False

        volume = self.default_volume_percent if volume_percent is None else volume_percent
        try:
            volume = max(0.0, min(100.0, float(volume)))
        except (TypeError, ValueError):
            logger.warning("Volume '%s' non valido: uso il valore predefinito %.0f%%.", volume, self.default_volume_percent)
            volume = self.default_volume_percent

        logger.info(
            "AVVIO annuncio RTP -> rtp://%s:%d | file: '%s' | volume: %.0f%% | priorita': %s",
            self.multicast_ip, self.multicast_port, os.path.basename(abs_path), volume, Priority(priority).name
        )
        return self.bus.play(
            audio, priority=priority, label=os.path.basename(abs_path), volume_percent=volume, queue=queue
        )

    # ──────────────────────────────────────────────────────────────────────
    # Utilita' interne
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _validate_file(abs_path: str) -> bool:
        """Controlla esistenza e consistenza minima del file audio da diffondere."""
        if not os.path.exists(abs_path):
            logger.error(
                "DISSUASIONE VOCALE NON ESEGUITA: file audio inesistente '%s'. "
                "Verificare il montaggio della cartella audio nel container.",
                abs_path
            )
            return False
        try:
            size_bytes = os.path.getsize(abs_path)
        except OSError as size_err:
            logger.error("Impossibile leggere il file audio '%s': %s", abs_path, size_err)
            return False
        if size_bytes == 0:
            logger.error("DISSUASIONE VOCALE NON ESEGUITA: file audio vuoto (0 byte): '%s'", abs_path)
            return False
        return True
