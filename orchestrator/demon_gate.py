#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — HEXAD DEMON Action Gate & Verifier
Modulo cibernetico deterministico a guardia degli attuatori fisici e dell'output vocale.

PRINCIPIO CARDINALE (Invarianza Ortogonale di HEXAD):
L'intelligenza stocastica (VLM / LLM) propone.
Il Gate deterministico (DEMON) verifica e decide con regole matematiche non negoziabili.
Nessun modello cloud ha l'autorità diretta di eccitare relè fisici o diffondere comandi non convalidati.
"""

import os
import time
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger("SentinelDemonGate")

class DemonActionGate:
    """Gate deterministico per attuatori fisici e conformità dell'output."""

    def __init__(self):
        self.last_gate_open_time = 0.0
        self.gate_cooldown_seconds = float(os.environ.get("DEMON_GATE_COOLDOWN_SECONDS", "60.0"))
        # Permetti apertura automatica solo se esplicitamente autorizzata da .env
        self.allow_auto_gate = os.environ.get("DEMON_ALLOW_AUTO_GATE", "false").lower() in ("true", "1", "yes")

    def authorize_gate_open(
        self,
        camera: str,
        orin_res: Dict[str, Any],
        is_armed: bool
    ) -> Tuple[bool, str]:
        """
        Verifica deterministica per l'apertura del cancello/portone.
        Regole sovrane inviolabili:
        1. Se il sistema è ARMATO (notte/chiusura), MAI aprire il cancello su sola base visiva (Anti-Spoofing).
        2. Cooldown minimo di 60s per proteggere i motori meccanici del cancello da attacchi o loop.
        3. Solo telecamere abilitate al varco carraio ('piazzale').
        4. Richiede abilitazione esplicita DEMON_ALLOW_AUTO_GATE=true per sicurezza fisica.
        """
        now = time.time()

        if not self.allow_auto_gate:
            return False, "DEMON BLOCK: Apertura automatica cancello disabilitata (DEMON_ALLOW_AUTO_GATE=false)"

        # Regola 1: Anti-Spoofing notturno (inviolabile)
        if is_armed:
            return False, "DEMON BLOCK: Sistema armato (notte/chiusura) — vietata apertura automatica su sola base visiva"

        # Regola 2: Protezione meccanica e cooldown
        if now - self.last_gate_open_time < self.gate_cooldown_seconds:
            remaining = int(self.gate_cooldown_seconds - (now - self.last_gate_open_time))
            return False, f"DEMON BLOCK: Cooldown motori cancello attivo (rimangono {remaining}s)"

        # Regola 3: Solo telecamere perimetrali carraie
        if camera not in ("piazzale", "varco_carrabile"):
            return False, f"DEMON BLOCK: La telecamera '{camera}' non presidia il varco carraio"

        # Regola 4: Verifica coerenza riconoscimento
        if not orin_res.get("is_president"):
            return False, "DEMON BLOCK: Nessuna identità autorizzata certificata"

        self.last_gate_open_time = now
        return True, "DEMON AUTHORIZED: Convalida deterministica superata con successo"

    @staticmethod
    def verify_spoken_thought(text: str, max_words: int = 25) -> Tuple[bool, str]:
        """
        Verifica di conformità PEIRA sull'output vocale prima della sintesi.
        1. Lunghezza entro max_words (evita monologhi o allucinazioni infinite).
        2. Rimozione di prompt injection o istruzioni di sistema sfuggite.
        """
        if not text or not text.strip():
            return False, ""

        clean = text.strip()
        words = clean.split()

        # Controllo lunghezza massima
        if len(words) > max_words:
            # Tronca chirurgicamente alla fine dell'ultima frase sensata entro max_words
            truncated = " ".join(words[:max_words])
            if "." in truncated:
                truncated = truncated.rsplit(".", 1)[0] + "."
            clean = truncated

        # Filtro parole di fuga o pattern anomali di injection
        forbidden_substrings = ["system prompt", "openrouter", "gemini", "chatgpt", "json:", "spoken_message"]
        lower = clean.lower()
        for f in forbidden_substrings:
            if f in lower:
                clean = clean.replace(f, "")

        clean = clean.strip()
        return bool(clean), clean


# Istanza singleton pronta all'uso
demon_gate = DemonActionGate()
