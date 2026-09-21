#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Driver Altoparlante IP (Fanvil A233)

MECCANISMO DI RIPRODUZIONE — MULTICAST RTP (collaudato in campo da Alessio)
--------------------------------------------------------------------------
L'A233 e' gia' configurato a bordo per ascoltare un canale MULTICAST RTP:
l'audio si invia come flusso RTP G.711 mu-law verso 239.255.1.1:5004 e lo
speaker lo diffonde immediatamente, senza alcuna chiamata SIP ne' HTTP.

Il comando di riferimento validato sul dispositivo reale e':

    ffmpeg -re -i <file.mp3> -af volume=<vol_float> -ac 1 -ar 8000
           -acodec pcm_mulaw -payload_type 0 -f rtp rtp://239.255.1.1:5004

NOTA STORICA: la precedente implementazione usava l'endpoint HTTP
`/cgi-bin/ConfigManApp.com?key=play:<file>`. Quell'endpoint NON fa parte
dell'API reale del firmware A233: rispondeva HTTP 200 ma non riproduceva
nulla. E' stato rimosso per non lasciare in campo un falso positivo.

REQUISITI OPERATIVI
- Il binario `ffmpeg` deve essere presente nel container (vedi Dockerfile).
- Il container deve avere `network_mode: host` in docker-compose.yml, altrimenti
  i pacchetti multicast restano confinati nel bridge Docker e non raggiungono
  l'interfaccia fisica su cui e' attestato il Fanvil.
- Sullo speaker vanno disattivati "Multicast Tone" e "Auto HangUp Tone",
  altrimenti al termine di ogni annuncio si sentono 3 bip (nota di Alessio).

CARATTERISTICHE
- Riproduzione in thread separato: non blocca mai il ciclo dell'orchestratore.
- Lock di mutua esclusione: un solo flusso ffmpeg alla volta (niente annunci
  sovrapposti e distorti sullo stesso canale multicast).
- Timeout di sicurezza calcolato sulla durata reale della traccia (ffprobe),
  con terminazione forzata dei processi ffmpeg eventualmente appesi.
- stderr di ffmpeg catturato e registrato nel log in caso di errore.
"""

import os
import shutil
import logging
import subprocess
import threading

logger = logging.getLogger("SentinelSpeaker")

# Parametri del canale multicast, sovrascrivibili da variabili d'ambiente.
DEFAULT_MULTICAST_IP = os.environ.get("FANVIL_MULTICAST_IP", "239.255.1.1")
DEFAULT_MULTICAST_PORT = int(os.environ.get("FANVIL_MULTICAST_PORT", "5004"))

# Volume di riproduzione predefinito in percentuale (0-100) quando il chiamante
# non ne passa uno: 70% corrisponde al filtro ffmpeg 'volume=0.7'.
DEFAULT_VOLUME_PERCENT = float(os.environ.get("FANVIL_DEFAULT_VOLUME", "70"))

# Margine aggiunto alla durata della traccia per il timeout di sicurezza, e
# timeout di ripiego quando la durata non e' determinabile.
PLAY_TIMEOUT_MARGIN = float(os.environ.get("FANVIL_PLAY_TIMEOUT_MARGIN", "10.0"))
PLAY_TIMEOUT_FALLBACK = float(os.environ.get("FANVIL_PLAY_TIMEOUT_FALLBACK", "120.0"))


class FanvilSpeakerController:
    """
    Driver di riproduzione vocale verso l'altoparlante Fanvil A233 via Multicast RTP.

    I parametri `host`, `http_port`, `user` e `password` sono conservati per
    compatibilita' con i chiamanti esistenti e per la sola diagnostica
    (raggiungibilita' del dispositivo): il percorso audio NON li usa piu'.
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

        # Mutua esclusione: garantisce un solo flusso ffmpeg attivo alla volta.
        self._play_lock = threading.Lock()
        # Riferimento al processo in corso, per poterlo terminare da stop().
        self._process = None
        self._process_lock = threading.Lock()
        # Distingue un'interruzione voluta da stop() da un vero errore di ffmpeg.
        self._stop_requested = False

        self.ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_bin = shutil.which("ffprobe")
        self._duration_cache = {}
        # Ritardo di pre-roll audio (default sicuro: 300ms concordato con Alessio)
        self.rtp_delay_ms = int(os.environ.get("FANVIL_RTP_DELAY_MS", "300"))

        if shutil.which("ffmpeg") is None:
            logger.error(
                "DISSUASIONE VOCALE NON DISPONIBILE: binario 'ffmpeg' non trovato nel container. "
                "Aggiungere 'ffmpeg' ai pacchetti apt-get del Dockerfile e ricostruire l'immagine."
            )

        # Precarica le durate di tutti gli MP3 per azzerare la latenza ffprobe durante gli allarmi
        self._preload_audio_durations()

        logger.info(
            "Driver Fanvil A233 in modalita' MULTICAST RTP -> rtp://%s:%d "
            "(G.711 mu-law, 8 kHz mono, volume predefinito %.0f%%, pre-roll delay %d ms)",
            self.multicast_ip, self.multicast_port, self.default_volume_percent, self.rtp_delay_ms
        )

    # ──────────────────────────────────────────────────────────────────────
    # Utilita' interne
    # ──────────────────────────────────────────────────────────────────────
    def _volume_to_float(self, volume_percent) -> float:
        """
        Converte il volume percentuale (0-100) nel moltiplicatore del filtro
        ffmpeg 'volume' (0.0-1.0): 10% -> 0.1, 85% -> 0.85, oltre 100% -> 1.0.
        Valori assenti o non numerici ricadono sul default (70% -> 0.7).
        """
        if volume_percent is None:
            volume_percent = self.default_volume_percent
        try:
            percent = float(volume_percent)
        except (TypeError, ValueError):
            logger.warning(
                "Volume '%s' non valido: uso il valore predefinito %.0f%%.",
                volume_percent, self.default_volume_percent
            )
            percent = self.default_volume_percent

        percent = max(0.0, min(100.0, percent))
        return round(percent / 100.0, 3)

    def _preload_audio_durations(self):
        """Pre-carica in memoria le durate di tutti i file MP3 noti all'avvio per eliminare la latenza ffprobe a runtime."""
        audio_dirs = [
            os.environ.get("AUDIO_DIR", "/app/audio"),
            os.path.join(os.path.dirname(__file__), "audio")
        ]
        count = 0
        for base_dir in audio_dirs:
            if not os.path.exists(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for f in files:
                    if f.lower().endswith(".mp3"):
                        full_path = os.path.abspath(os.path.join(root, f))
                        dur = self._probe_duration(full_path)
                        if dur:
                            count += 1
        if count > 0:
            logger.info("Pre-caricate in memoria le durate di %d file audio MP3 (zero latenza ffprobe).", count)

    def _probe_duration(self, abs_path: str):
        """Restituisce la durata in secondi della traccia via ffprobe (con cache in memoria)."""
        if abs_path in self._duration_cache:
            return self._duration_cache[abs_path]
        if not self.ffprobe_bin:
            return None
        try:
            probe = subprocess.run(
                [
                    self.ffprobe_bin, "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    abs_path,
                ],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=5.0
            )
            val = float(probe.stdout.decode("utf-8", "ignore").strip())
            self._duration_cache[abs_path] = val
            return val
        except Exception:
            return None

    def _validate_file(self, abs_path: str) -> bool:
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

    def build_command(self, abs_path: str, volume_float: float) -> list:
        """
        Costruisce il comando ffmpeg per lo streaming RTP multicast verso Fanvil A233.
        Usa adelay={delay}|{delay} (default 300ms concordato con Alessio) per concedere
        all'altoparlante il tempo hardware di aprire l'amplificatore senza tagliare la prima parola,
        risparmiando 500ms rispetto al vecchio valore di 800ms.
        """
        delay = self.rtp_delay_ms
        return [
            self.ffmpeg_bin,
            "-hide_banner", "-loglevel", "warning", "-nostdin",
            "-re",
            "-i", abs_path,
            "-af", f"adelay={delay}|{delay},volume={volume_float}",
            "-ac", "1",
            "-ar", "8000",
            "-acodec", "pcm_mulaw",
            "-payload_type", "0",
            "-f", "rtp",
            f"rtp://{self.multicast_ip}:{self.multicast_port}",
        ]

    # ──────────────────────────────────────────────────────────────────────
    # API pubblica
    # ──────────────────────────────────────────────────────────────────────
    def is_playing(self) -> bool:
        """True se un annuncio e' attualmente in riproduzione."""
        return self._play_lock.locked()

    def stop(self):
        """Termina immediatamente l'annuncio in corso (se presente)."""
        with self._process_lock:
            proc = self._process
            self._stop_requested = True
        if proc and proc.poll() is None:
            logger.info("Interruzione del flusso RTP in corso (PID %s).", proc.pid)
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()

    def play_audio_file(self, audio_filepath: str, volume_percent=None):
        """
        Diffonde il file MP3 indicato sull'altoparlante Fanvil via Multicast RTP.

        Non blocca il chiamante: il comando ffmpeg viene eseguito in un thread
        dedicato. Se un annuncio e' gia' in corso la richiesta viene scartata
        (un solo flusso per volta sullo stesso canale multicast).

        volume_percent: volume 0-100; se None usa FANVIL_DEFAULT_VOLUME (70).
        Restituisce True se la riproduzione e' stata avviata, False se scartata.
        """
        abs_path = os.path.abspath(audio_filepath)
        if not self._validate_file(abs_path):
            return False

        # Il lock si acquisisce QUI, non nel thread: cosi' il valore restituito e'
        # autorevole (niente corsa fra il controllo e l'avvio del worker) e il
        # chiamante sa subito se l'annuncio e' stato accettato o scartato.
        # Il rilascio avviene nel worker, al termine del processo ffmpeg.
        if not self._play_lock.acquire(blocking=False):
            logger.warning(
                "Annuncio '%s' SCARTATO: una riproduzione e' gia' in corso sul canale %s:%d.",
                os.path.basename(abs_path), self.multicast_ip, self.multicast_port
            )
            return False

        try:
            t = threading.Thread(
                target=self._play_worker,
                args=(abs_path, volume_percent),
                name="FanvilRTPPlayer",
                daemon=True
            )
            t.start()
        except Exception:
            # Il thread non e' partito: il lock va restituito subito, altrimenti
            # il canale resterebbe bloccato per sempre.
            self._play_lock.release()
            raise
        return True

    # ──────────────────────────────────────────────────────────────────────
    # Worker di riproduzione
    # ──────────────────────────────────────────────────────────────────────
    def _play_worker(self, abs_path: str, volume_percent):
        # ATTENZIONE: entra qui con self._play_lock GIA' acquisito da
        # play_audio_file(). Il blocco finally e' l'unico punto che lo rilascia.
        proc = None
        try:
            with self._process_lock:
                self._stop_requested = False
            volume_float = self._volume_to_float(volume_percent)
            # Recupera durata dalla cache in memoria; se non presente usa fallback a 10s senza bloccare su ffprobe
            duration = self._duration_cache.get(abs_path)
            timeout = (duration + PLAY_TIMEOUT_MARGIN) if duration else 20.0
            command = self.build_command(abs_path, volume_float)

            logger.info(
                "AVVIO annuncio RTP -> rtp://%s:%d | file: '%s' | volume: %s%% (%.3f) | durata: %s | comando: %s",
                self.multicast_ip, self.multicast_port, os.path.basename(abs_path),
                "default" if volume_percent is None else volume_percent, volume_float,
                f"{duration:.1f}s" if duration else "sconosciuta",
                " ".join(command)
            )

            proc = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
            with self._process_lock:
                self._process = proc

            try:
                _, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.error(
                    "TIMEOUT annuncio '%s' dopo %.1fs: processo ffmpeg appeso, terminazione forzata.",
                    os.path.basename(abs_path), timeout
                )
                proc.terminate()
                try:
                    proc.communicate(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                return

            stderr_text = stderr.decode("utf-8", "ignore").strip() if stderr else ""

            with self._process_lock:
                stopped_on_purpose = self._stop_requested

            if stopped_on_purpose:
                logger.info(
                    "Annuncio '%s' interrotto su richiesta (stop): canale %s:%d di nuovo libero.",
                    os.path.basename(abs_path), self.multicast_ip, self.multicast_port
                )
            elif proc.returncode == 0:
                logger.info(
                    "FINE annuncio '%s' diffuso su rtp://%s:%d (ffmpeg uscita 0).%s",
                    os.path.basename(abs_path), self.multicast_ip, self.multicast_port,
                    f" Avvisi ffmpeg: {stderr_text[:300]}" if stderr_text else ""
                )
            else:
                logger.error(
                    "DISSUASIONE VOCALE FALLITA: ffmpeg uscito con codice %d per '%s' su rtp://%s:%d. stderr: %s",
                    proc.returncode, os.path.basename(abs_path), self.multicast_ip,
                    self.multicast_port, stderr_text[:600] or "(vuoto)"
                )

        except FileNotFoundError:
            logger.error(
                "DISSUASIONE VOCALE FALLITA: binario ffmpeg non eseguibile ('%s'). "
                "Aggiungere 'ffmpeg' al Dockerfile e ricostruire l'immagine del container.",
                self.ffmpeg_bin
            )
        except Exception as exc:
            logger.exception("Errore imprevisto nella riproduzione multicast RTP: %s", exc)
        finally:
            with self._process_lock:
                self._process = None
            self._play_lock.release()
