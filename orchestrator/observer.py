#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Orchestratore Attivo (Fase 2: Decision Maker)

Ruolo:
- Connessione al broker MQTT locale (Mosquitto) con credenziali di ambiente.
- Ascolto degli eventi generati da Frigate ('frigate/events', 'frigate/reviews', 'frigate/tracked_object_update').
- Decision Engine:
  1. Persona rilevata (in piazzale o varchi):
     - Accende il Faretto (Relè Canale 1) per FARETTO_DURATION_SECONDS (es. 30s).
     - Riproduce l'avviso vocale di dissuasione ('03_avviso_dissuasione.mp3' o '04_allarme_intrusione.mp3').
     - Archivia foto e clip sul NAS Ugreen ('sentinel-eventi').
  2. Targa autorizzata al varco carrabile:
     - Dà l'impulso al Cancello (Relè Canale 2) per 3 secondi.
     - Riproduce l'avviso vocale ('02_targa_autorizzata.mp3').
     - Registra il transito sul NAS.
  3. Rumori anomali (urla, allarme incendio):
     - Accende immediatamente il faretto e notifica l'evento.
- Meccanismo di Cooldown (Antirimbalzo):
  - Evita che lo stesso allarme vocale si ripeta ogni frazione di secondo se la persona continua a muoversi.
- Mantiene la registrazione diagnostica JSON Lines in 'sentinel_events.log' per replay e audit.
"""

import os
import sys
import time
import json
import socket
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
import paho.mqtt.client as mqtt

# Moduli attuatori e servizi della Fase 2
from relay_controller import WaveshareRelayController
from speaker_controller import FanvilSpeakerController
from nas_archiver import UgreenNASArchiver

# ──────────────────────────────────────────────────────────────────────────────
# 1. PARAMETRI DI RUNTIME
# ──────────────────────────────────────────────────────────────────────────────
# Nomi dei servizi come richiesti da .env: validi in rete bridge Docker.
# Con 'network_mode: host' (necessario per il multicast RTP verso il Fanvil) i nomi
# dei container NON sono risolvibili: vengono convertiti in 127.0.0.1 dalla funzione
# resolve_service_host() piu' sotto, che entrambe le porte pubblicano gia' su loopback.
MQTT_HOST_PREFERRED = os.environ.get("FRIGATE_MQTT_HOST", "mosquitto")
MQTT_PORT = 1883
MQTT_USER = os.environ.get("FRIGATE_MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("FRIGATE_MQTT_PASSWORD", "")

LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
LOG_FILE = os.path.join(LOG_DIR, "sentinel_events.log")
AUDIO_BASE_DIR = os.environ.get("AUDIO_DIR", "/app/audio")

# Selezione pacchetto vocale ('carmelo' o 'sami')
VOICE_PACK = os.environ.get("SENTINEL_VOICE_PACK", "carmelo").lower()

# Parametri temporizzazioni
FARETTO_DURATION = float(os.environ.get("FARETTO_DURATION_SECONDS", "30.0"))
AUDIO_COOLDOWN = float(os.environ.get("AUDIO_COOLDOWN_SECONDS", "90.0"))

# Parametri Hardware
RELAY_HOST = os.environ.get("RELAY_HOST", "192.168.1.30")
RELAY_PORT = int(os.environ.get("RELAY_PORT", "4196"))

# Mappatura Canali Relè Waveshare (1-based da .env -> convertiti in 0-based per Modbus)
# Di default tutti i fari puntano al Canale 1 (faretto del banco di test)
RELAY_CHANNEL_PIAZZALE = max(0, int(os.environ.get("RELAY_CHANNEL_PIAZZALE", "1")) - 1)
RELAY_CHANNEL_VARCO_PEDONALE = max(0, int(os.environ.get("RELAY_CHANNEL_VARCO_PEDONALE", "1")) - 1)
RELAY_CHANNEL_VARCO_CARRABILE = max(0, int(os.environ.get("RELAY_CHANNEL_VARCO_CARRABILE", "1")) - 1)
RELAY_CHANNEL_CANCELLO = max(0, int(os.environ.get("RELAY_CHANNEL_CANCELLO", "2")) - 1)

CAMERA_RELAY_MAP = {
    "piazzale": RELAY_CHANNEL_PIAZZALE,
    "varco_pedonale": RELAY_CHANNEL_VARCO_PEDONALE,
    "varco_carrabile": RELAY_CHANNEL_VARCO_CARRABILE,
}

SPEAKER_HOST = os.environ.get("SPEAKER_HOST", "192.168.1.31")
SPEAKER_PORT = int(os.environ.get("SPEAKER_PORT", "80"))
SPEAKER_USER = os.environ.get("SPEAKER_USER", "admin")
SPEAKER_PASSWORD = os.environ.get("SPEAKER_PASSWORD", "admin")

# Canale MULTICAST RTP su cui il Fanvil A233 e' gia' in ascolto (collaudo Alessio).
FANVIL_MULTICAST_IP = os.environ.get("FANVIL_MULTICAST_IP", "239.255.1.1")
FANVIL_MULTICAST_PORT = int(os.environ.get("FANVIL_MULTICAST_PORT", "5004"))
# Volume di ripiego (0-100) quando system_settings.json non e' leggibile.
FANVIL_DEFAULT_VOLUME = float(os.environ.get("FANVIL_DEFAULT_VOLUME", "70"))

# API interna di Frigate usata dall'archiviatore NAS per scaricare foto e clip.
FRIGATE_HOST_PREFERRED = os.environ.get("FRIGATE_HOST", "frigate")
FRIGATE_PORT = int(os.environ.get("FRIGATE_PORT", "5000"))

NAS_IP = os.environ.get("NAS_IP", "192.168.1.11")
NAS_SHARE = os.environ.get("NAS_SHARE", "sentinel-eventi")
NAS_USER = os.environ.get("NAS_USER", "jetson")
NAS_PASSWORD = os.environ.get("NAS_PASSWORD", "Confprov33")

# File di stato Watchdog TensorRT (Segnalazione Alessio anti-freeze)
DETECTOR_STATUS_FILE = os.environ.get(
    "DETECTOR_STATUS_FILE",
    "/config/detector_status.json" if os.path.exists("/config") else os.path.join(os.path.dirname(__file__), "..", "config", "detector_status.json")
)

# ──────────────────────────────────────────────────────────────────────────────
# 2. LOGGERS
# ──────────────────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("SentinelOrchestrator")
logger.setLevel(logging.INFO)

console_formatter = logging.Formatter(fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Logger JSON Lines puro per file
jsonl_logger = logging.getLogger("SentinelEventLog")
jsonl_logger.setLevel(logging.INFO)
jsonl_logger.propagate = False
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
file_handler.setFormatter(logging.Formatter(fmt="%(message)s"))
jsonl_logger.addHandler(file_handler)

# ──────────────────────────────────────────────────────────────────────────────
# 2B. RISOLUZIONE HOST DEI SERVIZI (compatibilita' bridge Docker / rete host)
# ──────────────────────────────────────────────────────────────────────────────
def resolve_service_host(preferred: str, fallback: str = "127.0.0.1") -> str:
    """
    Restituisce 'preferred' se il nome e' risolvibile (rete bridge Docker), altrimenti
    'fallback'. Serve a rendere trasparente il passaggio a 'network_mode: host',
    imposto dal multicast RTP verso il Fanvil: in quella modalita' i nomi dei
    container ('mosquitto', 'frigate') non esistono, ma le rispettive porte sono
    gia' pubblicate su 127.0.0.1 dal docker-compose.
    """
    try:
        socket.getaddrinfo(preferred, None)
        return preferred
    except socket.gaierror:
        logger.warning(
            "Host di servizio '%s' non risolvibile (rete host attiva?): ripiego su '%s'.",
            preferred, fallback
        )
        return fallback

MQTT_HOST = resolve_service_host(MQTT_HOST_PREFERRED)
FRIGATE_HOST = resolve_service_host(FRIGATE_HOST_PREFERRED)

# ──────────────────────────────────────────────────────────────────────────────
# 3. INIZIALIZZAZIONE ATTUATORI
# ──────────────────────────────────────────────────────────────────────────────
relay = WaveshareRelayController(host=RELAY_HOST, port=RELAY_PORT)
speaker = FanvilSpeakerController(
    host=SPEAKER_HOST,
    http_port=SPEAKER_PORT,
    user=SPEAKER_USER,
    password=SPEAKER_PASSWORD,
    multicast_ip=FANVIL_MULTICAST_IP,
    multicast_port=FANVIL_MULTICAST_PORT,
    default_volume_percent=FANVIL_DEFAULT_VOLUME,
)
nas = UgreenNASArchiver(
    nas_ip=NAS_IP, share_name=NAS_SHARE, user=NAS_USER, password=NAS_PASSWORD,
    frigate_host=FRIGATE_HOST, frigate_port=FRIGATE_PORT
)

# Tracciamento cooldown per telecamera/azione: { "camera_azione": timestamp_ultimo_trigger }
cooldown_tracker = {}

# Tracciamento deduplicazione archiviazione NAS per event_id
archived_snapshots = set()
archived_clips = set()
MAX_TRACKED_EVENTS = 2000

def is_in_cooldown(key: str, cooldown_seconds: float) -> bool:
    now = time.time()
    last_time = cooldown_tracker.get(key, 0.0)
    if now - last_time < cooldown_seconds:
        return True
    cooldown_tracker[key] = now
    return False

def mark_snapshot_archived(event_id: str) -> bool:
    """Restituisce True solo la prima volta per un dato event_id (evita burst di salvataggi)."""
    if not event_id:
        return True
    if event_id in archived_snapshots:
        return False
    if len(archived_snapshots) > MAX_TRACKED_EVENTS:
        archived_snapshots.clear()
    archived_snapshots.add(event_id)
    return True

def mark_clip_archived(event_id: str) -> bool:
    """Restituisce True solo la prima volta che viene archiviata la clip di un evento."""
    if not event_id:
        return True
    if len(archived_clips) > MAX_TRACKED_EVENTS:
        archived_clips.clear()
    archived_clips.add(event_id)
    return True

def get_voice_pack() -> str:
    """Restituisce il pacchetto vocale attivo, verificando dinamicamente system_settings.json o fallback su env."""
    settings_file = os.environ.get("SETTINGS_FILE", "/config/system_settings.json")
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                pack = cfg.get("voice_pack", cfg.get("voice_gender", VOICE_PACK)).lower()
                if pack in ("carmelo", "male"):
                    return "carmelo"
                elif pack in ("sami", "female"):
                    return "sami"
                return pack
        except Exception:
            pass
    return VOICE_PACK

def get_voice_volume() -> float:
    """
    Restituisce il volume di diffusione corrente in percentuale (0-100).

    Fonte primaria: 'voice_volume' di system_settings.json, cioe' il cursore che
    l'operatore muove dalla dashboard; la lettura e' fatta a ogni annuncio, quindi
    una modifica ha effetto immediato senza riavviare l'orchestratore.
    Fonte di ripiego: FANVIL_DEFAULT_VOLUME (default 70%).
    """
    settings_file = os.environ.get("SETTINGS_FILE", "/config/system_settings.json")
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                value = json.load(f).get("voice_volume")
            if value is not None:
                return max(0.0, min(100.0, float(value)))
        except Exception as err:
            logger.warning(
                "Volume non leggibile da '%s' (%s): uso il valore predefinito %.0f%%.",
                settings_file, err, FANVIL_DEFAULT_VOLUME
            )
    return FANVIL_DEFAULT_VOLUME

def get_audio_path(sound_id: str) -> str:
    """Restituisce il percorso assoluto del file audio per il pacchetto vocale attivo."""
    pack = get_voice_pack()
    pack_folder = os.path.join(AUDIO_BASE_DIR, pack)
    if not os.path.exists(pack_folder):
        pack_folder = os.path.join(AUDIO_BASE_DIR, "carmelo")
    return os.path.join(pack_folder, f"{sound_id}.mp3")

def trigger_person_deterrence(camera: str, zone: str = None):
    """Trigger immediato faretto e voce vocale: latenza < 100ms dal primo frame con cooldown per zona."""
    loc_key = zone if zone else camera
    # 1. Accensione Faretto immediata
    relay_channel = CAMERA_RELAY_MAP.get(camera, RELAY_CHANNEL_PIAZZALE)
    if not is_in_cooldown(f"{loc_key}_faretto", cooldown_seconds=5.0):
        logger.info(">>> AZIONE IMMEDIATA: Persona rilevata su '%s' (loc: %s) -> Accensione Faretto (Relè Ch %d) per %ds", camera, loc_key, relay_channel + 1, int(FARETTO_DURATION))
        relay.accendi_faretto(channel=relay_channel, durata_secondi=FARETTO_DURATION)

    # 2. Avviso Vocale Fanvil Multicast RTP immediato con cooldown dedicato per zona/camera
    if not is_in_cooldown(f"{loc_key}_audio", cooldown_seconds=AUDIO_COOLDOWN):
        audio_file = get_audio_path("03_avviso_dissuasione")
        volume = get_voice_volume()
        logger.info(
            ">>> AZIONE IMMEDIATA: Riproduzione avviso vocale '%s' per '%s' [loc: %s] (multicast RTP %s:%d, volume %.0f%%)",
            os.path.basename(audio_file), camera, loc_key, FANVIL_MULTICAST_IP, FANVIL_MULTICAST_PORT, volume
        )
        speaker.play_audio_file(audio_file, volume_percent=volume)

# ──────────────────────────────────────────────────────────────────────────────
# 4. LOGICA DI DECISIONE E AZIONE (RULES ENGINE)
# ──────────────────────────────────────────────────────────────────────────────
def handle_frigate_event(event_data: dict, topic: str):
    """Elabora gli eventi di tracciamento oggetti da 'frigate/events'."""
    event_type = event_data.get("type") # 'new', 'update', 'end'
    after = event_data.get("after", {})
    if not after:
        return

    event_id = after.get("id")
    camera = after.get("camera", "unknown")
    label = after.get("label", "unknown")
    is_false_positive = after.get("false_positive", False)
    has_snapshot = after.get("has_snapshot", False)
    has_clip = after.get("has_clip", False)
    current_zones = after.get("current_zones", []) or after.get("entered_zones", [])
    active_zone = current_zones[0] if current_zones else None

    if is_false_positive:
        return

    # Scenario A: RILEVAMENTO PERSONA (Varco pedonale, piazzale o carrabile)
    if label == "person":
        if event_type in ("new", "update"):
            # Attivazione deterrenza (faro + voce) con cooldown per zona
            trigger_person_deterrence(camera, zone=active_zone)

            # 3. Archiviazione Snapshot sul NAS (una sola volta per ID evento, istantanea)
            if has_snapshot and mark_snapshot_archived(event_id):
                nas.archive_snapshot(event_id=event_id, camera=camera, label=label)

        elif event_type == "end":
            # 4. Archiviazione Clip Video sul NAS solo a conclusione dell'evento (attesa 6s per flush MP4 da Frigate)
            if has_clip and mark_clip_archived(event_id):
                logger.info(">>> Evento concluso su '%s' (ID: %s). Avvio download clip video (delay 6s)...", camera, event_id)
                nas.archive_clip(event_id=event_id, camera=camera, label=label, delay_seconds=6.0)

    # Scenario B: RILEVAMENTO VEICOLO (Varco carrabile o piazzale)
    elif label in ("car", "truck", "motorcycle"):
        if event_type in ("new", "update"):
            if has_snapshot and mark_snapshot_archived(event_id):
                logger.info(">>> Rilevato veicolo (%s) su '%s' (ID: %s). Archiviazione snapshot...", label, camera, event_id)
                nas.archive_snapshot(event_id=event_id, camera=camera, label=label)
        elif event_type == "end":
            if has_clip and mark_clip_archived(event_id):
                nas.archive_clip(event_id=event_id, camera=camera, label=label, delay_seconds=6.0)

def handle_lpr_update(lpr_data: dict):
    """Elabora le letture targa pubblicate su 'frigate/tracked_object_update'."""
    if lpr_data.get("type") != "lpr":
        return

    plate = lpr_data.get("plate")
    name = lpr_data.get("name") # Se presente in known_plates
    score = lpr_data.get("score", 0.0)
    camera = lpr_data.get("camera", "varco_carrabile")

    logger.info(">>> LPR: Targa letta '%s' (Nome: %s, Confidenza: %.2f) su %s", plate, name, score, camera)

    # Se la targa è riconosciuta (nota) con alta confidenza
    if name is not None and score >= 0.85:
        if not is_in_cooldown("cancello_apertura", cooldown_seconds=10.0):
            logger.info(">>> AZIONE: Targa autorizzata '%s' (%s) -> Apertura Cancello (Relè Canale %d) + Voce", plate, name, RELAY_CHANNEL_CANCELLO + 1)
            relay.apri_cancello(channel=RELAY_CHANNEL_CANCELLO, impulso_secondi=3.0)
            speaker.play_audio_file(get_audio_path("02_targa_autorizzata"), volume_percent=get_voice_volume())
    elif name is None and score >= 0.85:
        # Targa sconosciuta
        if not is_in_cooldown("cancello_non_autorizzato", cooldown_seconds=15.0):
            logger.info(">>> AZIONE: Targa NON autorizzata '%s' -> Avviso dissuasione vocale", plate)
            speaker.play_audio_file(get_audio_path("05_targa_non_autorizzata"), volume_percent=get_voice_volume())

def handle_audio_alarm(topic: str, value: str):
    """Elabora rilevamenti audio di emergenza ('frigate/<camera>/audio/<type>')."""
    if value.upper() == "ON":
        logger.warning(">>> ALLARME AUDIO RILEVATO su topic %s: Valore=%s -> Accensione faretto immediata", topic, value)
        relay.accendi_faretto(channel=RELAY_CHANNEL_PIAZZALE, durata_secondi=45.0)
        speaker.play_audio_file(get_audio_path("04_allarme_intrusione"), volume_percent=get_voice_volume())

# ──────────────────────────────────────────────────────────────────────────────
# 4B. WATCHDOG ANTI-FREEZE TENSORRT (SEGNALAZIONE CRITICA ALESSIO)
# ──────────────────────────────────────────────────────────────────────────────
watchdog_state = {
    "last_detection_time": time.time(),
    "last_stats_time": time.time(),
    "status": "standby",
    "detection_fps": 0.0,
    "cameras_active": False,
    "frozen_alert_sent": False
}

def save_detector_status(data: dict):
    """Scrive atomicamente lo stato del watchdog su disco per la dashboard."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(DETECTOR_STATUS_FILE)), exist_ok=True)
        tmp_file = f"{DETECTOR_STATUS_FILE}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_file, DETECTOR_STATUS_FILE)
    except Exception as e:
        logger.warning("Impossibile salvare %s: %s", DETECTOR_STATUS_FILE, e)

def handle_frigate_stats(stats: dict):
    """
    Watchdog Anti-Freeze TensorRT (Segnalazione di Alessio):
    Monitora i metrici di Frigate pubblicati su 'frigate/stats'.
    Se i flussi video sono attivi (camera_fps > 0) ma il detector non elabora
    frame (detection_fps == 0.0) per oltre 60 secondi, rileva il blocco
    silenzioso di TensorRT e notifica lo stato di ALLARME CRITICO.
    """
    now = time.time()
    watchdog_state["last_stats_time"] = now

    detectors = stats.get("detectors", {})
    tensorrt_stat = detectors.get("tensorrt", {})
    detection_fps = float(stats.get("detection_fps", tensorrt_stat.get("detection_fps", 0.0)))
    inference_speed = float(tensorrt_stat.get("inference_speed", 0.0))

    cameras = stats.get("cameras", {})
    cameras_active = any(float(c.get("camera_fps", 0.0)) > 0.5 for c in cameras.values())
    watchdog_state["cameras_active"] = cameras_active

    if detection_fps > 0.0:
        watchdog_state["last_detection_time"] = now
        watchdog_state["status"] = "healthy"
        watchdog_state["detection_fps"] = detection_fps
        watchdog_state["frozen_alert_sent"] = False
        save_detector_status({
            "healthy": True,
            "status": "healthy",
            "detection_fps": round(detection_fps, 1),
            "inference_speed_ms": round(inference_speed, 1),
            "cameras_active": cameras_active,
            "alert": None,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    else:
        elapsed = now - watchdog_state["last_detection_time"]
        if cameras_active and elapsed > 60.0:
            watchdog_state["status"] = "frozen"
            if not watchdog_state["frozen_alert_sent"]:
                logger.critical(
                    ">>> [CRITICAL WATCHDOG] RILEVATORE TENSORRT CONGELATO! "
                    "Flussi video attivi ma nessun frame elaborato da %.1f secondi! Container Docker healthy ma inferenza bloccata.",
                    elapsed
                )
                watchdog_state["frozen_alert_sent"] = True

            save_detector_status({
                "healthy": False,
                "status": "frozen",
                "detection_fps": 0.0,
                "inference_speed_ms": 0.0,
                "cameras_active": True,
                "frozen_seconds": round(elapsed),
                "alert": "RILEVAMENTO BLOCCATO",
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
        else:
            status_text = "waiting" if cameras_active else "standby"
            watchdog_state["status"] = status_text
            save_detector_status({
                "healthy": True,
                "status": status_text,
                "detection_fps": 0.0,
                "inference_speed_ms": round(inference_speed, 1),
                "cameras_active": cameras_active,
                "alert": None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            })

ZONE_CAMERA_MAP = {
    "zona_transito_pedoni": "varco_pedonale",
    "zona_accesso_veicoli": "varco_carrabile",
    "zona_parcheggio": "piazzale",
    "zona_perimetro": "piazzale"
}

def handle_rapid_person_topic(topic: str, payload_str: str):
    """
    Intercetta all'istante qualsiasi notifica MQTT di presenza persona.
    Gestisce conteggi numerici ("1", "2"), flag binari ("ON", "true"),
    sia a livello di telecamera che a livello di singola zona.
    """
    parts = topic.split("/")
    if len(parts) < 3:
        return
    target = parts[1]
    clean_val = payload_str.strip().upper()
    is_active = False
    if clean_val in ("ON", "TRUE", "ACTIVE"):
        is_active = True
    else:
        try:
            is_active = float(clean_val) > 0
        except ValueError:
            pass

    if is_active:
        cam_name = ZONE_CAMERA_MAP.get(target, target)
        logger.info(
            ">>> TRIGGER IMMEDIATO PERSONA: intercettato topic '%s' (payload: '%s') -> telecamera '%s' [loc: %s]",
            topic, payload_str, cam_name, target
        )
        trigger_person_deterrence(cam_name, zone=target)

def handle_frigate_review(review_data: dict):
    """Gestisce gli eventi review (Frigate 0.14+) per notifica o allerta tempestiva."""
    if not isinstance(review_data, dict):
        return
    after = review_data.get("after", {})
    if not after:
        return
    camera = after.get("camera", "piazzale")
    severity = after.get("severity", "")
    data = after.get("data", {})
    objects = data.get("objects", [])
    if "person" in objects or severity == "alert":
        logger.info(">>> ALLERTA REVIEW FRIGATE: Persona rilevata su '%s' (severity: %s)", camera, severity)
        trigger_person_deterrence(camera)

# ──────────────────────────────────────────────────────────────────────────────
# 5. CALLBACK MQTT
# ──────────────────────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if not reason_code.is_failure:
        logger.info("Connessione stabilita con successo al broker MQTT (%s:%d)", MQTT_HOST, MQTT_PORT)
        client.subscribe("frigate/#", qos=0)
        logger.info("Sentinel AI Orchestrator attivo su 'frigate/#' — decision engine operativo.")
    else:
        logger.error("Fallimento connessione al broker MQTT (%s:%d): %s", MQTT_HOST, MQTT_PORT, reason_code)

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    if reason_code.is_failure:
        logger.warning("Disconnessione imprevista dal broker MQTT. Riconnessione in corso...")
    else:
        logger.info("Disconnessione ordinaria dal broker MQTT.")

def on_message(client, userdata, msg):
    topic = msg.topic
    raw_payload = msg.payload
    payload_len = len(raw_payload)
    iso_timestamp = datetime.now(timezone.utc).astimezone().isoformat()

    # Verifica binaria (UTF-8 strict)
    try:
        text_payload = raw_payload.decode("utf-8")
        is_binary = False
    except UnicodeDecodeError:
        is_binary = True

    record = {
        "timestamp": iso_timestamp,
        "topic": topic,
        "payload_bytes": payload_len
    }

    if is_binary:
        record["type"] = "binary"
    else:
        parsed_json = None
        if (text_payload.startswith("{") and text_payload.endswith("}")) or (text_payload.startswith("[") and text_payload.endswith("]")):
            try:
                parsed_json = json.loads(text_payload)
            except Exception:
                parsed_json = None

        if parsed_json is not None:
            record["type"] = "json"
            record["payload"] = parsed_json

            # DISPATCHER EVENTI AL DECISION ENGINE
            if topic == "frigate/events":
                handle_frigate_event(parsed_json, topic)
            elif topic == "frigate/reviews":
                handle_frigate_review(parsed_json)
            elif topic == "frigate/tracked_object_update":
                handle_lpr_update(parsed_json)
            elif topic == "frigate/stats":
                handle_frigate_stats(parsed_json)

        else:
            record["type"] = "text"
            record["payload"] = text_payload

            # CONTROLLO TOPIC AUDIO RAPIDI (es. frigate/<cam>/audio/scream ON)
            if "/audio/" in topic and any(alarm in topic for alarm in ("scream", "yell", "fire_alarm")):
                handle_audio_alarm(topic, text_payload)

            # TRIGGER ISTANTANEO PERSONA (camera o zona, conteggio numerico o ON/OFF)
            elif topic.startswith("frigate/") and "/person" in topic:
                handle_rapid_person_topic(topic, text_payload)

    # Scrittura su log JSON Lines (audit e replay)
    json_line = json.dumps(record, ensure_ascii=False, separators=(',', ':'))
    jsonl_logger.info(json_line)

# ──────────────────────────────────────────────────────────────────────────────
# 6. AVVIO
# ──────────────────────────────────────────────────────────────────────────────
def main():
    logger.info("════════════════════════════════════════════════════════════════════")
    logger.info("CONF-LAVORO SENTINEL AI — ORCHESTRATORE ATTIVO (FASE 2)")
    logger.info("Broker: %s:%d | Utente: %s", MQTT_HOST, MQTT_PORT, MQTT_USER)
    logger.info("API Frigate: http://%s:%d", FRIGATE_HOST, FRIGATE_PORT)
    logger.info("Relè Waveshare: %s:%d (Canale 1: Faretto, Canale 2: Cancello)", RELAY_HOST, RELAY_PORT)
    logger.info(
        "Altoparlante Fanvil %s: MULTICAST RTP rtp://%s:%d (Pacchetto voce: '%s', volume %.0f%%)",
        SPEAKER_HOST, FANVIL_MULTICAST_IP, FANVIL_MULTICAST_PORT, VOICE_PACK, get_voice_volume()
    )
    logger.info("NAS Ugreen: %s (Condivisione: '%s', Utente: '%s')", NAS_IP, NAS_SHARE, NAS_USER)
    logger.info("════════════════════════════════════════════════════════════════════")

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="sentinel_ai_orchestrator")
    if MQTT_USER and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    backoff = 2
    connected = False
    while not connected:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            connected = True
        except Exception as err:
            logger.warning("Broker MQTT non ancora disponibile (%s). Riprovo tra %ds...", err, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

    try:
        client.loop_forever(retry_first_connection=True)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Arresto orchestratore...")
        client.disconnect()
        logger.info("Orchestratore arrestato.")

if __name__ == "__main__":
    main()
