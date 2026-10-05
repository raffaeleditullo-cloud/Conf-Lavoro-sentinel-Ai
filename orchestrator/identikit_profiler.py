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
        self.speaker = None
        self.relay = None
        self.mqtt_client = None
        self.voice_arbiter = None
        self.get_volume = None
        self.get_audio_path = None
        self._analyzed_events = set()

    def init_context(
        self,
        speaker=None,
        relay=None,
        mqtt_client=None,
        voice_arbiter=None,
        get_volume=None,
        get_audio_path=None
    ):
        """Inietta i riferimenti ai controller attivi senza duplicare i moduli in runtime."""
        self.speaker = speaker
        self.relay = relay
        self.mqtt_client = mqtt_client
        self.voice_arbiter = voice_arbiter
        self.get_volume = get_volume
        self.get_audio_path = get_audio_path

    def _claim_thought(self, camera: str):
        """Chiede la parola all'arbitro della voce (sempre concessa se non configurato)."""
        if self.voice_arbiter is None:
            from voice_arbiter import ThoughtGrant
            return ThoughtGrant(granted=True)
        return self.voice_arbiter.claim_thought(camera)

    def _play_recorded_warning(self, camera: str):
        """Ripiego: diffonde l'avviso registrato di dissuasione con la priorita' del pensiero."""
        if not self.speaker:
            return
        from rtp_audio_bus import Priority
        audio_file = self.get_audio_path("03_avviso_dissuasione") if self.get_audio_path else "/app/audio/carmelo/03_avviso_dissuasione.mp3"
        vol = self.get_volume() if self.get_volume else 100.0
        logger.info(">>> [ORIN FALLBACK] Avviso vocale registrato '%s' per '%s'", os.path.basename(audio_file), camera)
        self.speaker.play_audio_file(audio_file, volume_percent=vol, priority=Priority.THOUGHT, queue=True)

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
        snapshot_bytes: bytes = None,
        is_armed: bool = True
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

        # Salva la scheda JSON su disco locale
        filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{camera}_{event_id[:8]}.json"
        local_path = os.path.join(self.log_dir, filename)
        try:
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug("Impossibile salvare identikit iniziale su disco: %s", e)

        # Arricchimento intelligente con ORIN BRAIN (Asincrono in background)
        self._trigger_orin_enrichment_async(
            profile=profile,
            event_id=event_id,
            camera=camera,
            local_json_path=local_path,
            snapshot_bytes=snapshot_bytes,
            is_armed=is_armed
        )

        return profile

    def _trigger_orin_enrichment_async(
        self,
        profile: dict,
        event_id: str,
        camera: str,
        local_json_path: str,
        snapshot_bytes: bytes = None,
        is_armed: bool = True
    ):
        """Avvia l'analisi visiva avanzata di ORIN in un thread separato senza bloccare il flusso principale."""
        # Deduplicazione: analizza ogni event_id una sola volta, evitando chiamate cloud duplicate per update continui
        if not event_id:
            return
        if event_id in self._analyzed_events:
            return
        self._analyzed_events.add(event_id)
        if len(self._analyzed_events) > 2000:
            self._analyzed_events.clear()

        import threading
        t = threading.Thread(
            target=self._run_orin_enrichment,
            args=(profile, event_id, camera, local_json_path, snapshot_bytes, is_armed),
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
        snapshot_bytes: bytes = None,
        is_armed: bool = True
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

        # Analisi Visiva ORIN con stato armamento reale
        orin_res = orin_brain.analyze_frame(img_data, camera=camera, is_armed=is_armed)
        if not orin_res or orin_res.get("fallback"):
            # Fallback di sicurezza: analisi cloud fallita a sistema armato. L'avviso registrato
            # serve solo se il riflesso non ha gia' parlato per questo rilevamento.
            if is_armed:
                try:
                    grant = self._claim_thought(camera)
                    if grant and not grant.reflex_voiced:
                        self._play_recorded_warning(camera)
                except Exception as e:
                    logger.warning("Errore fallback audio: %s", e)
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
            # Il client viene iniettato da observer.on_connect: niente 'import observer',
            # che ricaricherebbe una seconda copia del modulo con controller duplicati.
            client = self.mqtt_client
            if client and client.is_connected():
                client.publish("sentinel/identikit", json.dumps(profile), qos=0)
        except Exception:
            pass

        # Azione A: Convalida deterministica HEXAD DEMON per apertura cancello carraio
        if orin_res.get("open_gate") or orin_res.get("is_president"):
            try:
                from demon_gate import demon_gate
                allowed, reason = demon_gate.authorize_gate_open(camera, orin_res, is_armed)
            except Exception:
                allowed, reason = False, "DEMON Gate non disponibile"

            if allowed:
                logger.info(">>> [DEMON ACTION GATE: AUTORIZZATO] Apertura cancello carraio per Presidente Roberto su '%s'", camera)
                try:
                    if self.relay:
                        self.relay.apri_cancello(channel=1, impulso_secondi=3.0)
                except Exception as e:
                    logger.warning("Impossibile azionare relè cancello per il Presidente: %s", e)
            else:
                logger.info(">>> [DEMON ACTION GATE: BLOCCATO] %s", reason)

        # Azione B: Sintesi vocale dinamica con ElevenLabs (Voce Carmelo)
        spoken_msg = orin_res.get("spoken_message")
        if spoken_msg:
            # Verifica deterministica PEIRA sulla sicurezza e brevità del testo
            try:
                from demon_gate import demon_gate
                is_valid, sanitized_msg = demon_gate.verify_spoken_thought(spoken_msg, max_words=22)
            except Exception:
                is_valid, sanitized_msg = True, spoken_msg

            if not is_valid or not sanitized_msg:
                sanitized_msg = spoken_msg

            # Se è il Presidente Roberto parla SEMPRE (accoglienza). Altrimenti, parla solo se il sistema è armato.
            should_speak = orin_res.get("is_president") or is_armed
            if should_speak:
                try:
                    grant = self._claim_thought(camera)
                    if grant:
                        vol = self.get_volume() if self.get_volume else 100.0
                        v_pack = "carmelo"
                        ok = orin_brain.speak(sanitized_msg, voice_pack=v_pack, volume_percent=vol)
                        if not ok and is_armed and not grant.reflex_voiced:
                            # Sintesi fallita e nessun riflesso pronunciato: avviso registrato
                            self._play_recorded_warning(camera)
                    else:
                        logger.info(">>> [ORIN VOICE] Annuncio vocale per '%s' soppresso: turno vocale gia' concesso.", camera)
                except Exception as e:
                    logger.warning("Impossibile diffondere voce ORIN: %s", e)


# Istanza pronta all'uso
identikit_profiler = IdentikitProfiler()
