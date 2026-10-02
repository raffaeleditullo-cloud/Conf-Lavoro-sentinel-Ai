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
        status_evaluation: str = None,
        snapshot_bytes: bytes = None
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

        # Arricchimento intelligente con ORIN BRAIN (Asincrono in background)
        self._trigger_orin_enrichment_async(
            profile=profile,
            event_id=event_id,
            camera=camera,
            local_json_path=local_path,
            snapshot_bytes=snapshot_bytes
        )

        return profile

    def _trigger_orin_enrichment_async(
        self,
        profile: dict,
        event_id: str,
        camera: str,
        local_json_path: str,
        snapshot_bytes: bytes = None
    ):
        """Avvia l'analisi visiva avanzata di ORIN in un thread separato senza bloccare il flusso principale."""
        import threading
        t = threading.Thread(
            target=self._run_orin_enrichment,
            args=(profile, event_id, camera, local_json_path, snapshot_bytes),
            name=f"OrinEnrichment-{event_id[:8]}",
            daemon=True
        )
        t.start()

    def _run_orin_enrichment(
        self,
        profile: dict,
        event_id: str,
        camera: str,
        local_json_path: str,
        snapshot_bytes: bytes = None
    ):
        """Esegue l'analisi con Gemini 2.5 Flash, gestisce l'accoglienza del Presidente e la voce dinamica."""
        try:
            from orin_brain import orin_brain
        except ImportError:
            return

        # Recupera i byte dello snapshot se non forniti direttamente
        img_data = snapshot_bytes
        if not img_data:
            # 1. Prova a leggere da /media/frigate/clips/
            clips_dir = os.environ.get("CLIPS_DIR", "/media/frigate/clips")
            local_clip_img = os.path.join(clips_dir, f"{camera}-{event_id}.jpg")
            if os.path.exists(local_clip_img):
                try:
                    with open(local_clip_img, "rb") as f:
                        img_data = f.read()
                except Exception:
                    pass

        # 2. Prova a scaricare dall'API locale di Frigate
        if not img_data:
            frigate_host = os.environ.get("FRIGATE_HOST", "127.0.0.1")
            frigate_port = int(os.environ.get("FRIGATE_PORT", "5000"))
            snap_url = f"http://{frigate_host}:{frigate_port}/api/events/{event_id}/snapshot.jpg"
            import urllib.request
            try:
                with urllib.request.urlopen(snap_url, timeout=2.0) as resp:
                    img_data = resp.read()
            except Exception:
                pass

        if not img_data:
            logger.debug("ORIN: Nessun fotogramma disponibile per l'evento %s", event_id)
            return

        # Analisi Visiva ORIN
        orin_res = orin_brain.analyze_frame(img_data, camera=camera, is_armed=True)
        if not orin_res or orin_res.get("fallback"):
            return

        # Aggiornamento scheda profilo
        profile["orin_intelligence"] = orin_res
        if orin_res.get("is_president"):
            profile["stato_valutazione"] = "PRESIDENTE RICONOSCIUTO: ROBERTO CAPOBIANCO — ACCOGLIENZA ATTIVA"

        # Riscrive il file JSON arricchito
        try:
            with open(local_json_path, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Pubblica aggiornamento via MQTT per la Dashboard
        try:
            import observer
            if observer._active_mqtt_client and observer._active_mqtt_client.is_connected():
                observer._active_mqtt_client.publish("sentinel/identikit", json.dumps(profile), qos=0)
        except Exception:
            pass

        # Azione A: Se è il Presidente Roberto, apri il cancello carraio automaticamente!
        if orin_res.get("open_gate") or orin_res.get("is_president"):
            logger.info(">>> [ORIN ACTION] Presidente Roberto riconosciuto al varco '%s': apertura cancello!", camera)
            try:
                import observer
                observer.relay.apri_cancello(channel=observer.RELAY_CHANNEL_CANCELLO, impulso_secondi=3.0)
            except Exception as e:
                logger.warning("Impossibile azionare relè cancello per il Presidente: %s", e)

        # Azione B: Sintesi vocale dinamica con ElevenLabs (Voce Carmelo)
        spoken_msg = orin_res.get("spoken_message")
        if spoken_msg:
            try:
                import observer
                vol = observer.get_voice_volume()
                v_pack = "carmelo"
                orin_brain.speak(spoken_msg, voice_pack=v_pack, volume_percent=vol)
            except Exception as e:
                logger.warning("Impossibile diffondere voce ORIN: %s", e)


# Istanza pronta all'uso
identikit_profiler = IdentikitProfiler()

