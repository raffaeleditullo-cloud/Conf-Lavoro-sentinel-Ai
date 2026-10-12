#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Arbitro della voce (chi puo' parlare, e quando)

IL PROBLEMA CHE RISOLVE
Prima il Riflesso/avviso immediato e la frase di ORIN condividevano la stessa
chiave di cooldown ('global_speaker_audio'): l'avviso immediato la occupava e,
2-3 secondi dopo, ORIN la trovava occupata e veniva silenziato quasi sempre.

IL MODELLO
Ogni rilevamento armato apre un "turno vocale" composto da due momenti:
  1. RIFLESSO  — la reazione immediata (Livello 0). Soggetto ai cooldown
                 storici: AUDIO_COOLDOWN_SECONDS per zona/telecamera e
                 SPEAKER_GLOBAL_COOLDOWN_SECONDS sull'intero impianto.
  2. PENSIERO  — la frase contestuale di ORIN. Se segue un riflesso della stessa
                 telecamera entro THOUGHT_WINDOW_SECONDS ne e' la continuazione
                 naturale e viene SEMPRE concesso, una sola volta.
                 Senza un riflesso associato (es. accoglienza del Presidente a
                 sistema disarmato) segue cooldown propri, separati da quelli
                 del riflesso.

Il turno del pensiero indica anche se il riflesso associato ha gia' parlato:
il ripiego di ORIN (analisi cloud o sintesi fallita -> traccia registrata) va
diffuso solo in caso contrario, per non ripetere due volte l'avviso.

Tutti i metodi sono thread-safe: vengono chiamati dal ciclo MQTT e dai thread ORIN.
"""

import os
import time
import logging
import threading
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger("SentinelVoiceArbiter")


@dataclass(frozen=True)
class ThoughtGrant:
    """Esito della richiesta di parola per il pensiero di ORIN."""
    granted: bool
    reflex_voiced: bool = False

    def __bool__(self) -> bool:
        return self.granted


class VoiceArbiter:
    """Concede la parola al riflesso e al pensiero senza che si blocchino a vicenda."""

    def __init__(
        self,
        local_cooldown: float = None,
        global_cooldown: float = None,
        thought_window: float = None,
    ):
        self.local_cooldown = float(
            local_cooldown if local_cooldown is not None else os.environ.get("AUDIO_COOLDOWN_SECONDS", "15")
        )
        self.global_cooldown = float(
            global_cooldown if global_cooldown is not None else os.environ.get("SPEAKER_GLOBAL_COOLDOWN_SECONDS", "20")
        )
        # Cooldown di sicurezza tra telecamere DIVERSE (evita annunci a raffica durante il transito)
        self.inter_camera_cooldown = float(
            os.environ.get("SPEAKER_INTER_CAMERA_COOLDOWN_SECONDS", "12.0")
        )
        self.thought_window = float(
            thought_window if thought_window is not None else os.environ.get("REFLEX_THOUGHT_WINDOW_SECONDS", "30")
        )

        self._lock = threading.Lock()
        # Riflessi
        self._reflex_global = 0.0
        self._last_reflex_camera: Optional[str] = None
        self._reflex_local: Dict[str, float] = {}
        # Turno aperto per telecamera: {camera: (istante_riflesso, riflesso_pronunciato)}
        self._pending: Dict[str, tuple] = {}
        # Pensieri senza riflesso associato
        self._thought_global = 0.0
        self._last_thought_camera: Optional[str] = None
        self._thought_local: Dict[str, float] = {}

    def claim_reflex(self, camera: str, loc_key: str = None, voiced: bool = True) -> bool:
        """
        Chiede la parola per il riflesso immediato.

        - Non sovrappone MAI un nuovo annuncio se l'altoparlante sta gia' parlando.
        - Se la telecamera e' DIVERSA da quella precedente, applica un cooldown inter-camera (12s)
          evitando sia il silenzio prolungato che il fuoco a raffica ping-pong.
        - Se la telecamera e' la STESSA (anche cambiando zona), applica il cooldown locale (15-20s).
        """
        loc_key = loc_key or camera
        now = time.monotonic()
        with self._lock:
            # 1. Non sovrapporre MAI la voce se l'altoparlante sta gia' trasmettendo un audio
            try:
                from rtp_audio_bus import get_audio_bus
                if get_audio_bus().is_playing():
                    logger.info("Voce: riflesso su '%s' soppresso: altoparlante gia' in riproduzione audio.", camera)
                    return False
            except Exception:
                pass

            is_diff_camera = (self._last_reflex_camera is not None and self._last_reflex_camera != camera)
            effective_global_cd = self.inter_camera_cooldown if is_diff_camera else self.global_cooldown

            if now - self._reflex_global < effective_global_cd:
                rem = effective_global_cd - (now - self._reflex_global)
                logger.info(
                    "Voce: riflesso su '%s' soppresso da cooldown %s (%.1fs rimanenti).",
                    loc_key,
                    "inter-camera" if is_diff_camera else "globale",
                    rem
                )
                return False

            if now - self._reflex_local.get(loc_key, 0.0) < self.local_cooldown:
                logger.info("Voce: riflesso su '%s' soppresso da cooldown locale (%.0fs).", loc_key, self.local_cooldown)
                return False

            self._reflex_global = now
            self._reflex_local[loc_key] = now
            self._last_reflex_camera = camera
            self._pending[camera] = (now, voiced)
            return True

    def claim_thought(self, camera: str) -> ThoughtGrant:
        """
        Chiede la parola per la frase di ORIN (o per il suo ripiego registrato).
        Il turno associato a un riflesso si consuma alla prima richiesta.
        """
        now = time.monotonic()
        with self._lock:
            pending = self._pending.pop(camera, None)
            if pending and now - pending[0] <= self.thought_window:
                self._mark_thought(camera, now)
                return ThoughtGrant(granted=True, reflex_voiced=pending[1])

            is_diff_camera = (self._last_thought_camera is not None and self._last_thought_camera != camera)
            effective_global_cd = self.inter_camera_cooldown if is_diff_camera else self.global_cooldown

            if now - self._thought_global < effective_global_cd:
                logger.info("Voce: pensiero su '%s' soppresso da cooldown (%.1fs).", camera, effective_global_cd)
                return ThoughtGrant(granted=False)
            if now - self._thought_local.get(camera, 0.0) < self.local_cooldown:
                logger.info("Voce: pensiero su '%s' soppresso da cooldown locale (%.0fs).", camera, self.local_cooldown)
                return ThoughtGrant(granted=False)
            self._mark_thought(camera, now)
            return ThoughtGrant(granted=True)

    def _mark_thought(self, camera: str, now: float):
        self._thought_global = now
        self._thought_local[camera] = now
        self._last_thought_camera = camera
