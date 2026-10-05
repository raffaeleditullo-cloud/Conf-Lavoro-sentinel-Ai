#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Livello 0: Riflesso immediato ("R2-D2")

Un droide non pensa prima di reagire: reagisce subito e poi elabora.
Al primo rilevamento il Riflesso diffonde in pochi millisecondi una frase breve
gia' pronta in RAM, mentre ORIN (Livello 1) elabora la frase contestuale che
seguira' senza pause sullo stesso canale.

LIBRERIA DELLE FRASI
  audio/reflex/<voce>/manifest.json   descrizione delle frasi (vedi sotto)
  audio/reflex/<voce>/<id>.ulaw       audio G.711 mu-law 8 kHz grezzo
Generata da scripts/generate_reflex_library.py. Tutto viene caricato in RAM
all'avvio: al momento dell'allarme non si legge alcun file e non si avvia
alcun processo.

  {"voice": "carmelo", "clips": [
     {"id": "r01", "file": "r01.ulaw", "text": "...",
      "stage": "first" | "repeat",          # primo passaggio o recidiva
      "time": "any" | "day" | "night",      # fascia oraria
      "cameras": ["corridoio"],             # vuoto = tutte
      "min_persons": 1}                     # numero minimo di persone
  ]}

SCELTA DELLA FRASE
Si filtrano le frasi compatibili con il contesto (telecamera, fascia oraria,
numero di persone, recidiva). Se nessuna corrisponde, i criteri si allentano
uno alla volta. Si evita di ripetere l'ultima frase usata.

RIPIEGO
Se la libreria della voce attiva non esiste ancora, si usano le tracce storiche
(03_avviso_dissuasione al primo passaggio, 04_allarme_intrusione in recidiva),
gia' decodificate in RAM: il comportamento resta quello collaudato.

PARAMETRI (variabili d'ambiente)
- REFLEX_ESCALATION_SECONDS: entro questo intervallo un nuovo riflesso sulla
  stessa telecamera e' considerato recidiva. Default 120.
- REFLEX_NIGHT_START / REFLEX_NIGHT_END: fascia notturna. Default 19:00 - 07:00.
"""

import os
import json
import random
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional

from rtp_audio_bus import AudioBus, Priority
from ulaw_audio import audio_library

logger = logging.getLogger("SentinelReflex")

STAGE_FIRST = "first"
STAGE_REPEAT = "repeat"

# Tracce storiche usate quando la libreria del Riflesso non e' disponibile.
LEGACY_TRACKS = {
    STAGE_FIRST: "03_avviso_dissuasione",
    STAGE_REPEAT: "04_allarme_intrusione",
}


@dataclass(frozen=True)
class ReflexClip:
    id: str
    text: str
    audio: bytes
    stage: str = STAGE_FIRST
    time: str = "any"
    cameras: tuple = ()
    min_persons: int = 1

    def matches(self, stage=None, period=None, camera=None, persons=None) -> bool:
        """Verifica la compatibilita'; un criterio None non viene controllato."""
        if stage is not None and self.stage != stage:
            return False
        if period is not None and self.time not in ("any", period):
            return False
        if camera is not None and self.cameras and camera not in self.cameras:
            return False
        if persons is not None and persons < self.min_persons:
            return False
        return True


class ReflexEngine:
    """Sceglie e diffonde il riflesso vocale immediato."""

    def __init__(
        self,
        bus: AudioBus,
        audio_base_dir: str,
        get_voice_pack: Callable[[], str],
        get_volume: Callable[[], float],
        get_audio_path: Callable[[str], str],
    ):
        self.bus = bus
        self.reflex_dir = os.path.join(audio_base_dir, "reflex")
        self.get_voice_pack = get_voice_pack
        self.get_volume = get_volume
        self.get_audio_path = get_audio_path

        self.escalation_seconds = float(os.environ.get("REFLEX_ESCALATION_SECONDS", "120"))
        self.night_start = os.environ.get("REFLEX_NIGHT_START", "19:00")
        self.night_end = os.environ.get("REFLEX_NIGHT_END", "07:00")

        self._lock = threading.Lock()
        self._library: Dict[str, List[ReflexClip]] = {}
        self._last_fire: Dict[str, float] = {}
        self._last_clip_id: Dict[str, str] = {}
        self.load()

    # ──────────────────────────────────────────────────────────────────────
    # Caricamento libreria
    # ──────────────────────────────────────────────────────────────────────
    def load(self):
        """Carica in RAM le librerie di tutte le voci presenti in audio/reflex/."""
        library: Dict[str, List[ReflexClip]] = {}
        if os.path.isdir(self.reflex_dir):
            for voice in sorted(os.listdir(self.reflex_dir)):
                clips = self._load_voice(os.path.join(self.reflex_dir, voice))
                if clips:
                    library[voice] = clips
        with self._lock:
            self._library = library

        if library:
            for voice, clips in library.items():
                logger.info("Riflesso L0: libreria '%s' pronta in RAM (%d frasi).", voice, len(clips))
        else:
            logger.warning(
                "Riflesso L0: nessuna libreria in '%s'. Uso le tracce storiche (03/04) come riflesso. "
                "Generarla con scripts/generate_reflex_library.py.", self.reflex_dir
            )

    @staticmethod
    def _load_voice(voice_dir: str) -> List[ReflexClip]:
        manifest_path = os.path.join(voice_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            return []
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, ValueError) as exc:
            logger.error("Riflesso L0: manifest non leggibile '%s': %s", manifest_path, exc)
            return []

        clips = []
        for entry in manifest.get("clips", []):
            audio = audio_library.get(os.path.join(voice_dir, entry.get("file", "")))
            if not audio:
                logger.warning("Riflesso L0: audio mancante per la frase '%s' in %s.", entry.get("id"), voice_dir)
                continue
            clips.append(ReflexClip(
                id=entry["id"],
                text=entry.get("text", ""),
                audio=audio,
                stage=entry.get("stage", STAGE_FIRST),
                time=entry.get("time", "any"),
                cameras=tuple(entry.get("cameras") or ()),
                min_persons=int(entry.get("min_persons", 1)),
            ))
        return clips

    # ──────────────────────────────────────────────────────────────────────
    # Contesto
    # ──────────────────────────────────────────────────────────────────────
    def _period(self, now: datetime) -> str:
        """'night' o 'day' in base alla fascia REFLEX_NIGHT_START - REFLEX_NIGHT_END."""
        cur = now.strftime("%H:%M")
        if self.night_start > self.night_end:            # fascia a cavallo della mezzanotte
            is_night = cur >= self.night_start or cur < self.night_end
        else:
            is_night = self.night_start <= cur < self.night_end
        return "night" if is_night else "day"

    def _select(self, voice: str, stage: str, period: str, camera: str, persons: int) -> Optional[ReflexClip]:
        with self._lock:
            clips = self._library.get(voice) or []
        if not clips:
            return None

        # Criteri allentati progressivamente: prima l'orario, poi la telecamera,
        # poi il numero di persone e infine la fase (prima volta / recidiva).
        attempts = [
            dict(stage=stage, period=period, camera=camera, persons=persons),
            dict(stage=stage, period=None, camera=camera, persons=persons),
            dict(stage=stage, period=None, camera=None, persons=persons),
            dict(stage=stage, period=None, camera=None, persons=None),
            dict(stage=None, period=None, camera=None, persons=None),
        ]
        for criteria in attempts:
            candidates = [c for c in clips if c.matches(**criteria)]
            if candidates:
                last_id = self._last_clip_id.get(camera)
                fresh = [c for c in candidates if c.id != last_id] or candidates
                return random.choice(fresh)
        return None

    # ──────────────────────────────────────────────────────────────────────
    # Azione
    # ──────────────────────────────────────────────────────────────────────
    def fire(self, camera: str, persons: int = 1) -> bool:
        """
        Diffonde il riflesso per la telecamera indicata.
        Va chiamato solo dopo che il VoiceArbiter ha concesso la parola.
        """
        t0 = time.monotonic()
        with self._lock:
            last = self._last_fire.get(camera, 0.0)
            self._last_fire[camera] = t0
        stage = STAGE_REPEAT if last and t0 - last <= self.escalation_seconds else STAGE_FIRST
        period = self._period(datetime.now())
        voice = self.get_voice_pack()
        volume = self.get_volume()

        clip = self._select(voice, stage, period, camera, max(1, int(persons)))
        if clip:
            self._last_clip_id[camera] = clip.id
            audio, label = clip.audio, f"riflesso:{voice}/{clip.id}"
            text = clip.text
        else:
            track_path = self.get_audio_path(LEGACY_TRACKS[stage])
            audio = audio_library.get(track_path)
            label, text = f"riflesso:storico/{os.path.basename(track_path)}", ""
            if not audio:
                logger.error("Riflesso L0: nessun audio disponibile per '%s' (traccia storica '%s').", camera, track_path)
                return False

        accepted = self.bus.play(audio, priority=Priority.REFLEX, label=label, volume_percent=volume)
        logger.info(
            ">>> [RIFLESSO L0] '%s' | fase %s | %s | persone %d | %s%s | decisione in %.1f ms",
            camera, stage, period, persons, label,
            f" \"{text}\"" if text else "",
            (time.monotonic() - t0) * 1000.0
        )
        return accepted
