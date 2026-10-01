#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — JEV Adaptive Contextual Decider
Basato sull'architettura Zero-Token Decision Making (stile JEV / Rizzo-Flow).

Questo modulo fornisce l'intelligenza contestuale auto-adattiva per le 3 telecamere:
1. 'piazzale'   (Esterno: Entrata magazzino, parcheggio auto, pensilina)
2. 'magazzino'  (Interno: Capannone, scaffali, bancali, scatoloni)
3. 'corridoio'  (Passaggio: Varco stretto di transito tra magazzino e azienda)

Consente al sistema di decidere se un rilevamento e' una reale minaccia da allarmare
senza bisogno di ricalibrare parametri matematici ad ogni installazione fisica.
"""

import os
import time
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("SentinelJevDecider")

# ──────────────────────────────────────────────────────────────────────────────
# PROFILI AMBIENTALI TELECAMERE (Certificati da sopralluogo visivo)
# ──────────────────────────────────────────────────────────────────────────────
ENVIRONMENT_PROFILES = {
    "piazzale": {
        "description": "Esterno: Piazzale di carico merci, portone scorrevole e parcheggio auto",
        "camera_height_m": 3.0,
        "environment_type": "outdoor_perimeter",
        "min_confidence": 0.70,
        "threat_criteria": [
            "Persona a piedi che si avvicina al portone o sosta nei pressi delle auto parcheggiate",
            "Movimento confermato con traiettoria orientata verso l'edificio",
        ],
        "suppression_criteria": [
            "Auto ferma nel parcheggio",
            "Ombre proiettate dalla pensilina o dal portone",
            "Sagome lontane o parzialmente occultate dal veicolo in primo piano",
        ],
        "aspect_ratio_min": 0.60,  # Tollerante per transiti a mezzo busto e prospettive ravvicinate
        "speed_threshold": 0.005,
    },
    "magazzino": {
        "description": "Interno: Capannone di stoccaggio, corsie, bancali e scatoloni",
        "camera_height_m": 3.5,
        "environment_type": "indoor_warehouse",
        "min_confidence": 0.60,
        "threat_criteria": [
            "Persona che cammina o si aggira all'interno delle corsie o verso l'area merci",
            "Movimento attivo continuo nello spazio libero centrale",
        ],
        "suppression_criteria": [
            "Scatoloni impilati e bancali fissi",
            "Sedie da ufficio nere con ruote ferme nell'area",
            "Materiali di imballaggio o teloni riflettenti a terra",
            "Ponteggi o scale metalliche",
        ],
        "aspect_ratio_min": 0.25,  # Tollerante per operatori chini, movimentazione merci e prospettive dall'alto
        "speed_threshold": 0.005,  # Movimenti più controllati/lenti tra gli scaffali
    },
    "corridoio": {
        "description": "Interno: Corridoio stretto di collegamento tra magazzino e azienda",
        "camera_height_m": 2.3,
        "environment_type": "indoor_chokepoint",
        "min_confidence": 0.55,
        "threat_criteria": [
            "Qualsiasi persona che entra nel corridoio e cammina verso la porta",
            "Punto di transito obbligato: massima priorità di reazione immediata",
        ],
        "suppression_criteria": [
            "Riflessi di luce artificiale sul pavimento lucido",
            "Porta di fondo che si apre senza sagoma umana completa",
        ],
        "aspect_ratio_min": 0.20,  # Tollerante per inquadrature longitudinali in prospettiva e varchi stretti
        "speed_threshold": 0.005,  # Transito pedonale rapido a passo normale
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# CLASSE DECISIONALE JEV
# ──────────────────────────────────────────────────────────────────────────────
class JevAdaptiveDecider:
    """Motore di decisione contestuale rapido auto-adattivo."""

    def __init__(self):
        self.enabled = os.environ.get("JEV_DECIDER_ENABLED", "true").lower() in ("true", "1", "yes")
        # Se presente un endpoint locale compatibile Rizzo-flow / JEV (opzionale)
        self.endpoint = os.environ.get("JEV_LOCAL_ENDPOINT", "")
        logger.info("JEV Adaptive Decider inizializzato (Attivo: %s, Endpoint: %s)", self.enabled, self.endpoint or "Local Heuristic Engine")

    def evaluate_threat(
        self,
        camera: str,
        label: str,
        box: list,
        score: float,
        displacement: float = 0.05,
        extra_context: Dict[str, Any] = None
    ) -> Tuple[bool, str, float]:
        """
        Valuta se l'oggetto rilevato rappresenta una minaccia reale per la specifica telecamera.
        Ritorna: (is_threat: bool, ragione: str, confidenza_finale: float)
        """
        if not self.enabled:
            return True, "Jev disabilitato - passaggio diretto", score

        # Recupera il profilo specifico della telecamera
        profile = ENVIRONMENT_PROFILES.get(camera)
        if not profile:
            # Fallback generico per telecamere non mappate
            return True, "Profilo generico standard", score

        # Se non è una persona (es. auto su piazzale)
        if label != "person":
            if camera == "piazzale" and label in ("car", "truck", "motorcycle"):
                return True, f"Veicolo in transito su {camera}", score
            return False, f"Oggetto {label} ignorato su {camera}", score

        # Calcolo proporzioni bounding box [ymin, xmin, ymax, xmax]
        if box and len(box) == 4:
            ymin, xmin, ymax, xmax = [float(c) for c in box]
            h = abs(ymax - ymin)
            w = abs(xmax - xmin)
            aspect_ratio = (h / w) if w > 0 else 1.0
        else:
            aspect_ratio = 1.5

        # 1. Valutazione Aspect Ratio specifico per il profilo ambientale (se abilitato da .env)
        human_ratio_enabled = os.environ.get("HUMAN_RATIO_FILTER_ENABLED", "true").lower() in ("true", "1", "yes")
        if human_ratio_enabled:
            required_ar = profile["aspect_ratio_min"]
            if aspect_ratio < required_ar:
                reason = f"[{camera.upper()}] Sagoma non umana per questo ambiente (H/W={aspect_ratio:.2f} < {required_ar:.2f})"
                logger.debug("JEV: %s", reason)
                return False, reason, score

        # 2. Valutazione Movimento Dinamico specifico per la camera
        speed_min = profile["speed_threshold"]
        if displacement < speed_min:
            reason = f"[{camera.upper()}] Oggetto statico o movimento insufficiente (delta={displacement:.3f} < {speed_min:.3f})"
            logger.debug("JEV: %s", reason)
            return False, reason, score

        # 3. Decisione di Minaccia Confermata
        reason = f"[{camera.upper()}] Allarme confermato dal profilo {profile['environment_type']} (H/W={aspect_ratio:.2f}, conf={score:.2f})"
        logger.info(">>> JEV DECISION: %s", reason)
        return True, reason, score

# Istanza singleton pronta all'uso
jev_decider = JevAdaptiveDecider()
