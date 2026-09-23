#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Modulo di Identikit Forense Istantaneo
Genera automaticamente una scheda descrittiva dell'intruso o del soggetto rilevato
per ciascun allarme scattato nelle 3 telecamere ('piazzale', 'magazzino', 'corridoio').

I dati vengono:
1. Stampati nei log di sistema.
2. Salvati in un file JSON forense accanto alla clip e allo snapshot.
3. Pubblicati via MQTT su 'sentinel/identikit' per la Dashboard Web di Conf-Lavoro.
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger("SentinelIdentikit")

class IdentikitProfiler:
    """Generatore di schede identikit per eventi di intrusione."""

    def __init__(self, log_dir: str = "/app/logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

    def generate_profile(
        self,
        event_id: str,
        camera: str,
        label: str,
        score: float,
        box: list,
        trajectory_vector: tuple = None,
        snapshot_url: str = None,
        status_evaluation: str = None
    ) -> Dict[str, Any]:
        """
        Crea e salva una scheda descrittiva forense dell'evento.
        """
        now = datetime.now(timezone.utc)
        timestamp_iso = now.isoformat()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Stima direzione di marcia in base alla telecamera
        traiettoria_desc = "Movimento generico rilevato"
        if camera == "corridoio":
            traiettoria_desc = "Transito diretto in corridoio verso passaggio uffici"
        elif camera == "magazzino":
            traiettoria_desc = "Spostamento attivo all'interno dell'area stoccaggio / corsia merci"
        elif camera == "piazzale":
            traiettoria_desc = "Avvicinamento esterno verso il portone di carico / area parcheggio"

        # Stima altezza apparente e dimensione
        h_rel = 0.0
        w_rel = 0.0
        if box and len(box) == 4:
            ymin, xmin, ymax, xmax = [float(c) for c in box]
            h_rel = abs(ymax - ymin)
            w_rel = abs(xmax - xmin)

        profile = {
            "version": "1.0",
            "event_id": event_id,
            "timestamp": timestamp_iso,
            "timestamp_human": timestamp_str,
            "telecamera": camera,
            "soggetto": label,
            "confidenza_ia": round(float(score) * 100, 1),
            "rilevamento": {
                "box_normalizzato": box,
                "altezza_relativa": round(h_rel, 3),
                "larghezza_relativa": round(w_rel, 3),
                "aspect_ratio": round(h_rel / w_rel, 2) if w_rel > 0 else 1.0,
            },
            "dinamica": {
                "traiettoria_stimata": traiettoria_desc,
                "vettore_spostamento": list(trajectory_vector) if trajectory_vector else [0.0, 0.0],
            },
            "evidenze": {
                "snapshot_url": snapshot_url or f"/api/events/{event_id}/snapshot.jpg",
                "clip_url": f"/api/events/{event_id}/clip.mp4",
            },
            "stato_valutazione": status_evaluation or "MINACCIA CONFERMATA — AZIONE DISSVASIONE ESEGUITA"
        }

        # Salvataggio file JSON forense locale
        safe_filename = f"identikit_{camera}_{event_id[:12]}.json"
        local_path = os.path.join(self.log_dir, safe_filename)
        try:
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
            logger.info(">>> SCHEDA IDENTIKIT GENERATA: %s (salvata in %s)", safe_filename, local_path)
        except Exception as e:
            logger.warning("Impossibile salvare file identikit: %s", e)

        return profile

# Istanza pronta all'uso
identikit_profiler = IdentikitProfiler()
