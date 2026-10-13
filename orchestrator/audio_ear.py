#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI // ORIN BRAIN — UNIVERSAL AUDIO EAR (PASS C)
Modulo di Ascolto Ambientale, Ingestione Microfono ALSA e Dialogo Bidirezionale.

Caratteristiche:
- Cattura audio nativa ALSA a 16 kHz 16-bit mono tramite arecord / ffmpeg.
- Gate Half-Duplex Deterministico: muta istantaneamente l'ascolto quando il Fanvil A233
  o l'AudioBus stanno riproducendo messaggi (zero feedback acustico).
- Voice Activity Detection (VAD) basato su energia e soglia RMS dBFS.
- Interfaccia diretta con OrinBrain.hear_and_respond() e sintesi ElevenLabs Turbo v2.5.
- Disattivabile e sicuro: se AUDIO_EAR_ENABLED=false o nessun microfono è presente,
  il modulo rimane inattivo senza bloccare l'orchestratore.
"""

import os
import io
import math
import time
import wave
import struct
import shutil
import logging
import threading
import subprocess
from typing import Optional, List

from rtp_audio_bus import get_audio_bus
from orin_brain import orin_brain

logger = logging.getLogger("SentinelAudioEar")


class AudioEar:
    """
    Ricevitore e analizzatore vocale ambientale per Conf-Lavoro Sentinel AI.
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        device: Optional[str] = None,
        sample_rate: int = 16000,
        vad_threshold_dbfs: Optional[float] = None,
        silence_timeout_sec: Optional[float] = None,
        min_speech_sec: Optional[float] = None,
        max_speech_sec: Optional[float] = None,
    ):
        raw_enabled = os.environ.get("AUDIO_EAR_ENABLED", "false").lower()
        self.enabled = (enabled if enabled is not None else raw_enabled in ("true", "1", "yes"))
        
        self.device = device or os.environ.get("AUDIO_INPUT_DEVICE", "plughw:0,0")
        self.sample_rate = int(sample_rate or os.environ.get("AUDIO_SAMPLE_RATE", "16000"))
        self.vad_threshold_dbfs = float(
            vad_threshold_dbfs if vad_threshold_dbfs is not None
            else os.environ.get("AUDIO_VAD_THRESHOLD_DBFS", "-44.0")
        )
        self.silence_timeout_sec = float(
            silence_timeout_sec if silence_timeout_sec is not None
            else os.environ.get("AUDIO_SILENCE_TIMEOUT_SEC", "0.9")
        )
        self.min_speech_sec = float(
            min_speech_sec if min_speech_sec is not None
            else os.environ.get("AUDIO_MIN_SPEECH_SEC", "0.5")
        )
        self.max_speech_sec = float(
            max_speech_sec if max_speech_sec is not None
            else os.environ.get("AUDIO_MAX_SPEECH_SEC", "9.0")
        )

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

        # Configurazione frame (100ms per ciclo VAD)
        self.frame_ms = 100
        self.frame_samples = (self.sample_rate * self.frame_ms) // 1000
        self.frame_bytes = self.frame_samples * 2  # 16-bit = 2 byte per campione

    def is_active(self) -> bool:
        """Verifica se l'orecchio è attivo e in ascolto continuo."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self):
        """Avvia il thread di ascolto se abilitato."""
        if not self.enabled:
            logger.info("AudioEar: disattivato da configurazione (AUDIO_EAR_ENABLED=false).")
            return

        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, name="SentinelAudioEar", daemon=True)
            self._thread.start()
            logger.info(
                "AudioEar avviato -> Dispositivo: '%s' | Rate: %d Hz | Soglia VAD: %.1f dBFS | Silenzio: %.1fs",
                self.device, self.sample_rate, self.vad_threshold_dbfs, self.silence_timeout_sec
            )

    def stop(self):
        """Arresta la cattura audio e termina il processo di registrazione."""
        with self._lock:
            self._running = False
            if self._proc:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=1.0)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("AudioEar arrestato.")

    def _open_capture_process(self) -> Optional[subprocess.Popen]:
        """Tenta di aprire il processo di cattura ALSA con arecord o ffmpeg."""
        # 1. Prova arecord (standard ALSA nativo su Linux/Jetson)
        if shutil.which("arecord"):
            cmd = [
                "arecord",
                "-D", self.device,
                "-f", "S16_LE",
                "-r", str(self.sample_rate),
                "-c", "1",
                "-t", "raw",
                "-q",
            ]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                # Verifica che non fallisca subito
                time.sleep(0.15)
                if proc.poll() is None:
                    return proc
                err = proc.stderr.read().decode("utf-8", errors="ignore").strip()
                logger.warning("arecord fallito per '%s': %s", self.device, err)
            except Exception as e:
                logger.debug("Tentativo arecord non riuscito: %s", e)

        # 2. Ripiego su ffmpeg (se arecord non è presente o fallisce)
        if shutil.which("ffmpeg"):
            cmd = [
                "ffmpeg",
                "-loglevel", "error",
                "-nostdin",
                "-f", "alsa",
                "-i", self.device,
                "-ar", str(self.sample_rate),
                "-ac", "1",
                "-f", "s16le",
                "-",
            ]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                time.sleep(0.15)
                if proc.poll() is None:
                    return proc
                err = proc.stderr.read().decode("utf-8", errors="ignore").strip()
                logger.warning("ffmpeg ALSA capture fallito per '%s': %s", self.device, err)
            except Exception as e:
                logger.debug("Tentativo ffmpeg ALSA non riuscito: %s", e)

        return None

    def _capture_loop(self):
        """Loop continuo di acquisizione audio e rilevamento parlato (VAD)."""
        retry_delay = 5.0

        while self._running:
            proc = self._open_capture_process()
            if not proc:
                logger.warning(
                    "AudioEar: impossibile accedere al dispositivo '%s'. Nuovo tentativo tra %.0fs...",
                    self.device, retry_delay
                )
                time.sleep(retry_delay)
                continue

            with self._lock:
                self._proc = proc

            logger.info("AudioEar: flusso di ascolto aperto con successo su '%s'.", self.device)
            speech_frames: List[bytes] = []
            is_speaking = False
            last_speech_time = 0.0
            speech_start_time = 0.0

            try:
                while self._running and proc.poll() is None:
                    # Legge esattamente un frame (100ms)
                    chunk = proc.stdout.read(self.frame_bytes)
                    if not chunk or len(chunk) < self.frame_bytes:
                        break

                    now = time.monotonic()

                    # 1. Gate Half-Duplex: se l'altoparlante o l'AudioBus sta parlando, azzera e ignora
                    if get_audio_bus().is_playing():
                        if is_speaking:
                            speech_frames.clear()
                            is_speaking = False
                        continue

                    # 2. Calcolo RMS e livello dBFS del frame
                    num_samples = len(chunk) // 2
                    samples = struct.unpack(f"<{num_samples}h", chunk)
                    rms = math.sqrt(sum(s**2 for s in samples) / num_samples)
                    dbfs = 20 * math.log10(rms / 32768.0) if rms > 0 else -999.0

                    # 3. Logica Voice Activity Detection (VAD)
                    if dbfs >= self.vad_threshold_dbfs:
                        if not is_speaking:
                            is_speaking = True
                            speech_start_time = now
                            logger.debug("AudioEar: rilevata voce (%.1f dBFS)", dbfs)
                        last_speech_time = now
                        speech_frames.append(chunk)
                    elif is_speaking:
                        speech_frames.append(chunk)
                        silence_duration = now - last_speech_time
                        total_duration = now - speech_start_time

                        # Fine parlato: silenzio prolungato o tempo massimo raggiunto
                        if silence_duration >= self.silence_timeout_sec or total_duration >= self.max_speech_sec:
                            if total_duration >= self.min_speech_sec:
                                raw_pcm = b"".join(speech_frames)
                                wav_data = self._pcm_to_wav(raw_pcm)
                                logger.info(
                                    "AudioEar: frase catturata (%.2fs, %d byte). Invio al cervello ORIN...",
                                    total_duration, len(wav_data)
                                )
                                # Invio asincrono a ORIN Brain per non bloccare la cattura continua
                                threading.Thread(
                                    target=self._dispatch_to_orin,
                                    args=(wav_data,),
                                    daemon=True
                                ).start()
                            else:
                                logger.debug("AudioEar: scartato rumore breve (%.2fs)", total_duration)

                            speech_frames.clear()
                            is_speaking = False

            except Exception as e:
                logger.warning("AudioEar: eccezione nel loop di cattura: %s", e)
            finally:
                try:
                    proc.terminate()
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
                with self._lock:
                    self._proc = None

            if self._running:
                logger.info("AudioEar: connessione persa, riapertura in corso...")
                time.sleep(1.0)

    def _pcm_to_wav(self, raw_pcm: bytes) -> bytes:
        """Inapsula campioni PCM grezzi (16-bit LE mono) in un contenitore WAV conforme."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(raw_pcm)
        return buf.getvalue()

    def _dispatch_to_orin(self, wav_data: bytes):
        """Consegna la frase catturata a OrinBrain per comprensione e risposta."""
        try:
            # Controllo di sicurezza: se nel frattempo un allarme prioritario è partito, non sovrapporsi
            if get_audio_bus().is_playing():
                logger.info("AudioEar: risposta soppressa, altoparlante attualmente occupato.")
                return

            res = orin_brain.hear_and_respond(
                audio_bytes=wav_data,
                voice_pack=os.environ.get("SENTINEL_VOICE_PACK", "carmelo"),
                play_response=True
            )
            logger.info("AudioEar: dialogo completato. Esito: %s", res.get("intent"))
        except Exception as e:
            logger.error("AudioEar: errore durante l'elaborazione del parlato con ORIN: %s", e)


# Istanza singleton globale pronta all'uso
audio_ear = AudioEar()
