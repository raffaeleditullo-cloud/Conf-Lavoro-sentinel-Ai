#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Codec G.711 mu-law e libreria audio in RAM

Il Fanvil A233 riceve audio G.711 mu-law, 8 kHz, mono (RTP payload type 0).
Questo modulo prepara l'audio in quel formato UNA SOLA VOLTA e lo tiene in RAM,
cosi' al momento dell'allarme non si avvia alcun processo e non si legge alcun file.

CONTENUTO
- Codec mu-law puro Python (conforme ITU-T G.711), usato per il volume digitale:
  la tabella di 256 valori si ricalcola solo quando cambia il volume, poi
  `bytes.translate()` la applica a costo trascurabile (codice C).
- `ensure_ulaw()`: normalizza in mu-law grezzo i dati ricevuti (WAV mu-law,
  mu-law grezzo, oppure MP3 come ultima risorsa tramite ffmpeg).
- `AudioLibrary`: cache delle tracce decodificate (i file .ulaw si leggono cosi'
  come sono, gli MP3 storici si decodificano con ffmpeg all'avvio, in background).
"""

import os
import shutil
import struct
import logging
import subprocess
import threading
from functools import lru_cache
from typing import Dict, Iterable, Optional, Tuple

logger = logging.getLogger("SentinelAudio")

SAMPLE_RATE = 8000
# Valore mu-law del silenzio digitale (campione lineare 0).
ULAW_SILENCE = 0xFF

_BIAS = 0x84
# Codifica su 14 bit come nel riferimento G.711 (Sun/CCITT): limite e fine segmenti.
_CLIP_14BIT = 8159
_SEG_END_14BIT = (0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF)


# ──────────────────────────────────────────────────────────────────────────────
# 1. CODEC G.711 MU-LAW
# ──────────────────────────────────────────────────────────────────────────────
def _ulaw_to_linear(u: int) -> int:
    """Decodifica un byte mu-law nel campione lineare a 16 bit corrispondente."""
    u = ~u & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    sample = (((mantissa << 3) + _BIAS) << exponent) - _BIAS
    return -sample if sign else sample


def linear_to_ulaw(sample: int) -> int:
    """
    Codifica un campione lineare a 16 bit in un byte mu-law.
    Identica al riferimento G.711 (stessi risultati di audioop.lin2ulaw).
    """
    pcm = sample >> 2                       # 14 bit; shift aritmetico come nel riferimento
    if pcm < 0:
        pcm, mask = -pcm, 0x7F
    else:
        mask = 0xFF
    pcm = min(pcm, _CLIP_14BIT) + (_BIAS >> 2)
    for segment, seg_end in enumerate(_SEG_END_14BIT):
        if pcm <= seg_end:
            return ((segment << 4) | ((pcm >> (segment + 1)) & 0x0F)) ^ mask
    return 0x7F ^ mask


ULAW_DECODE_TABLE = tuple(_ulaw_to_linear(u) for u in range(256))


@lru_cache(maxsize=16)
def volume_table(volume_percent: int) -> bytes:
    """
    Tabella di traduzione mu-law -> mu-law per il volume indicato (0-100).
    Equivale al filtro ffmpeg 'volume=<percent/100>' usato in precedenza.
    """
    gain = max(0, min(100, int(volume_percent))) / 100.0
    return bytes(linear_to_ulaw(int(round(ULAW_DECODE_TABLE[u] * gain))) for u in range(256))


def apply_volume(audio: bytes, volume_percent: float) -> bytes:
    """Applica il volume digitale a un buffer mu-law (100% = invariato)."""
    percent = int(round(max(0.0, min(100.0, float(volume_percent)))))
    if percent >= 100:
        return audio
    return audio.translate(volume_table(percent))


def silence(duration_ms: int) -> bytes:
    """Buffer mu-law di silenzio della durata indicata."""
    return bytes([ULAW_SILENCE]) * (SAMPLE_RATE * max(0, int(duration_ms)) // 1000)


# ──────────────────────────────────────────────────────────────────────────────
# 2. NORMALIZZAZIONE IN MU-LAW GREZZO
# ──────────────────────────────────────────────────────────────────────────────
def _parse_wav_ulaw(data: bytes) -> Optional[bytes]:
    """
    Estrae i campioni da un WAV mu-law 8 kHz mono (formato 7).
    Restituisce None se il WAV e' in un formato diverso (va decodificato con ffmpeg).
    """
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    pos = 12
    fmt_ok = False
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        chunk_size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + chunk_size]
        if chunk_id == b"fmt " and len(body) >= 16:
            audio_format, channels, rate = struct.unpack("<HHI", body[:8])
            fmt_ok = audio_format == 7 and channels == 1 and rate == SAMPLE_RATE
        elif chunk_id == b"data":
            return body if fmt_ok else None
        pos += 8 + chunk_size + (chunk_size & 1)
    return None


def _ffmpeg_to_ulaw(source: str, stdin_data: Optional[bytes] = None) -> Optional[bytes]:
    """Decodifica qualsiasi formato audio in mu-law grezzo 8 kHz mono tramite ffmpeg."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error("Decodifica audio impossibile: binario 'ffmpeg' non presente (sorgente: %s).", source)
        return None
    cmd = [
        ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", "pipe:0" if stdin_data is not None else source,
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "mulaw", "pipe:1",
    ]
    try:
        result = subprocess.run(
            cmd, input=stdin_data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30.0
        )
    except Exception as exc:
        logger.error("Decodifica ffmpeg fallita per '%s': %s", source, exc)
        return None
    if result.returncode != 0 or not result.stdout:
        logger.error(
            "Decodifica ffmpeg fallita per '%s' (codice %d): %s",
            source, result.returncode, result.stderr.decode("utf-8", "ignore")[:300]
        )
        return None
    return result.stdout


def ensure_ulaw(data: bytes, declared: str = "ulaw", source: str = "buffer") -> Optional[bytes]:
    """
    Restituisce `data` come mu-law grezzo 8 kHz mono.

    declared: formato dichiarato da chi ha prodotto i dati.
      - "ulaw": mu-law atteso (es. ElevenLabs output_format=ulaw_8000). Se arriva
        comunque con intestazione WAV o come MP3 (ID3) viene gestito.
      - qualsiasi altro valore: decodifica con ffmpeg.
    """
    if not data:
        return None
    if data[:4] == b"RIFF":
        samples = _parse_wav_ulaw(data)
        if samples is not None:
            return samples
        return _ffmpeg_to_ulaw(source, stdin_data=data)
    if declared == "ulaw" and data[:3] != b"ID3":
        return data
    return _ffmpeg_to_ulaw(source, stdin_data=data)


# ──────────────────────────────────────────────────────────────────────────────
# 3. LIBRERIA DELLE TRACCE IN RAM
# ──────────────────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = (".ulaw", ".mp3", ".wav")


class AudioLibrary:
    """
    Cache in RAM delle tracce gia' convertite in mu-law.
    La chiave e' il percorso assoluto: se il file cambia (mtime) viene riletto.
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[float, bytes]] = {}
        self._lock = threading.Lock()

    def get(self, path: str) -> Optional[bytes]:
        """Restituisce la traccia in mu-law (dalla cache se gia' pronta)."""
        abs_path = os.path.abspath(path)
        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            logger.error("Traccia audio inesistente: '%s'", abs_path)
            return None
        with self._lock:
            cached = self._cache.get(abs_path)
        if cached and cached[0] == mtime:
            return cached[1]

        audio = self._load(abs_path)
        if audio:
            with self._lock:
                self._cache[abs_path] = (mtime, audio)
        return audio

    @staticmethod
    def _load(abs_path: str) -> Optional[bytes]:
        if abs_path.lower().endswith(".ulaw"):
            try:
                with open(abs_path, "rb") as f:
                    return f.read() or None
            except OSError as exc:
                logger.error("Lettura traccia '%s' fallita: %s", abs_path, exc)
                return None
        return _ffmpeg_to_ulaw(abs_path)

    def preload(self, directories: Iterable[str]) -> int:
        """Converte e mette in RAM tutte le tracce presenti nelle cartelle indicate."""
        count = 0
        for base_dir in directories:
            if not base_dir or not os.path.isdir(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for name in files:
                    if name.lower().endswith(SUPPORTED_EXTENSIONS) and self.get(os.path.join(root, name)):
                        count += 1
        return count

    def preload_async(self, directories: Iterable[str]) -> threading.Thread:
        """Avvia il precaricamento in background, senza ritardare l'avvio del servizio."""
        dirs = list(directories)

        def _worker():
            count = self.preload(dirs)
            logger.info("Libreria audio: %d tracce pronte in RAM in formato mu-law (zero ffmpeg in allarme).", count)

        t = threading.Thread(target=_worker, name="AudioPreload", daemon=True)
        t.start()
        return t


audio_library = AudioLibrary()
