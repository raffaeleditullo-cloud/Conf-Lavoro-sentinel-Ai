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
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
import paho.mqtt.client as mqtt

# Moduli attuatori e servizi della Fase 2
from relay_controller import WaveshareRelayController
from speaker_controller import FanvilSpeakerController
from nas_archiver import UgreenNASArchiver
from jev_decider import jev_decider
from identikit_profiler import identikit_profiler
from reolink_spotlight import reolink_spotlight
from voice_arbiter import VoiceArbiter
from reflex_engine import ReflexEngine
from rtp_audio_bus import Priority

# ──────────────────────────────────────────────────────────────────────────────
# 1. PARAMETRI DI RUNTIME
# ──────────────────────────────────────────────────────────────────────────────
MQTT_HOST_PREFERRED = os.environ.get("FRIGATE_MQTT_HOST", os.environ.get("MQTT_HOST", "mosquitto"))
MQTT_PORT = int(os.environ.get("FRIGATE_MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("FRIGATE_MQTT_USER", "sentinel")
MQTT_PASSWORD = os.environ.get("FRIGATE_MQTT_PASSWORD", "")

LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
LOG_FILE = os.path.join(LOG_DIR, "sentinel_events.log")
AUDIO_BASE_DIR = os.environ.get("AUDIO_DIR", "/app/audio")

# Selezione pacchetto vocale ('carmelo' o 'sami')
VOICE_PACK = os.environ.get("SENTINEL_VOICE_PACK", "carmelo").lower()

# Parametri temporizzazioni e illuminazione
FARETTO_DURATION = float(os.environ.get("FARETTO_DURATION_SECONDS", "30.0"))
USE_REOLINK_SPOTLIGHT = os.environ.get("USE_REOLINK_SPOTLIGHT", "true").lower() in ("true", "1", "yes")
USE_EXTERNAL_RELAY_LIGHT = os.environ.get("USE_EXTERNAL_RELAY_LIGHT", "false").lower() in ("true", "1", "yes")
AUDIO_COOLDOWN = float(os.environ.get("AUDIO_COOLDOWN_SECONDS", "15.0"))
SPEAKER_GLOBAL_COOLDOWN = float(os.environ.get("SPEAKER_GLOBAL_COOLDOWN_SECONDS", "20.0"))

# Livello 0 — Riflesso immediato: frase breve gia' in RAM diffusa al primo rilevamento,
# seguita senza pause dalla frase contestuale di ORIN (vedi reflex_engine.py).
REFLEX_ENABLED = os.environ.get("REFLEX_ENABLED", "true").lower() in ("true", "1", "yes")

# Pezzettino 1: Filtro di Buonsenso per le Sagome (stile Jev / Calibrated Decision)
# Disabilitato di default (false) per non scartare persone reali a mezzo busto o a distanza ravvicinata nei test
HUMAN_RATIO_FILTER_ENABLED = os.environ.get("HUMAN_RATIO_FILTER_ENABLED", "false").lower() in ("true", "1", "yes")
MIN_HUMAN_ASPECT_RATIO = float(os.environ.get("MIN_HUMAN_ASPECT_RATIO", "0.20"))
MAX_PERSON_AREA_RATIO = float(os.environ.get("MAX_PERSON_AREA_RATIO", "0.95"))

# Pezzettino 2: Filtro di Movimento Dinamico & Traiettoria (Early Threat / Anti-Static)
# Sopprime gli allarmi se la sagoma rimane ferma o ha oscillazioni minime (< 2.5% schermo)
MOVEMENT_FILTER_ENABLED = os.environ.get("MOVEMENT_FILTER_ENABLED", "true").lower() in ("true", "1", "yes")
MIN_MOVEMENT_DISTANCE = float(os.environ.get("MIN_MOVEMENT_DISTANCE", "0.025"))

# Parametri Hardware
RELAY_HOST = os.environ.get("RELAY_HOST", "192.168.1.30")
RELAY_PORT = int(os.environ.get("RELAY_PORT", "4196"))

# Mappatura Canali Relè Waveshare (1-based da .env -> convertiti in 0-based per Modbus)
# Canale 1: Faretto Piazzale/Magazzino, Canale 2: Cancello/Portone
RELAY_CHANNEL_PIAZZALE = max(0, int(os.environ.get("RELAY_CHANNEL_PIAZZALE", "1")) - 1)
RELAY_CHANNEL_MAGAZZINO = max(0, int(os.environ.get("RELAY_CHANNEL_MAGAZZINO", "1")) - 1)
RELAY_CHANNEL_CORRIDOIO = max(0, int(os.environ.get("RELAY_CHANNEL_CORRIDOIO", "1")) - 1)
RELAY_CHANNEL_CANCELLO = max(0, int(os.environ.get("RELAY_CHANNEL_CANCELLO", "2")) - 1)

CAMERA_RELAY_MAP = {
    # Nuovi nomi del magazzino fisico
    "piazzale": RELAY_CHANNEL_PIAZZALE,
    "magazzino": RELAY_CHANNEL_MAGAZZINO,
    "corridoio": RELAY_CHANNEL_CORRIDOIO,
    # Alias storici per retrocompatibilità
    "varco_pedonale": RELAY_CHANNEL_MAGAZZINO,
    "varco_carrabile": RELAY_CHANNEL_PIAZZALE,
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

_settings_cache = {}
_settings_mtime = 0.0

def _get_cached_settings() -> dict:
    """Carica system_settings.json con cache in RAM; rilegge da disco solo se il file viene modificato."""
    global _settings_cache, _settings_mtime
    settings_file = os.environ.get("SETTINGS_FILE", "/config/system_settings.json")
    if os.path.exists(settings_file):
        try:
            mtime = os.path.getmtime(settings_file)
            if mtime != _settings_mtime:
                with open(settings_file, "r", encoding="utf-8") as f:
                    _settings_cache = json.load(f)
                _settings_mtime = mtime
        except Exception:
            pass
    return _settings_cache

def get_voice_pack() -> str:
    """Restituisce il pacchetto vocale attivo (lettura da RAM cache a zero I/O)."""
    cfg = _get_cached_settings()
    pack = cfg.get("voice_pack", cfg.get("voice_gender", VOICE_PACK)).lower()
    if pack in ("carmelo", "male"):
        return "carmelo"
    elif pack in ("sami", "female"):
        return "sami"
    return pack

def get_voice_volume() -> float:
    """Restituisce il volume di diffusione corrente in percentuale (lettura da RAM cache a zero I/O)."""
    cfg = _get_cached_settings()
    value = cfg.get("voice_volume")
    if value is not None:
        try:
            return max(0.0, min(100.0, float(value)))
        except (ValueError, TypeError):
            pass
    return FANVIL_DEFAULT_VOLUME

def get_audio_path(sound_id: str) -> str:
    """Restituisce il percorso assoluto del file audio per il pacchetto vocale attivo."""
    pack = get_voice_pack()
    cfg = _get_cached_settings()
    # Se il trigger richiede l'avviso standard, usa la traccia attiva configurata (es. identikit o avviso)
    track_name = cfg.get("active_track", sound_id) if sound_id == "03_avviso_dissuasione" else sound_id
    pack_folder = os.path.join(AUDIO_BASE_DIR, pack)
    if not os.path.exists(pack_folder):
        pack_folder = os.path.join(AUDIO_BASE_DIR, "carmelo")
    track_path = os.path.join(pack_folder, f"{track_name}.mp3")
    if not os.path.exists(track_path):
        track_path = os.path.join(pack_folder, "03_avviso_dissuasione.mp3")
    return track_path

# Arbitro della voce: riflesso e pensiero di ORIN non condividono piu' lo stesso cooldown.
voice_arbiter = VoiceArbiter(local_cooldown=AUDIO_COOLDOWN, global_cooldown=SPEAKER_GLOBAL_COOLDOWN)

# Livello 0 — Riflesso immediato (libreria di frasi caricata in RAM all'avvio)
reflex = ReflexEngine(
    bus=speaker.bus,
    audio_base_dir=AUDIO_BASE_DIR,
    get_voice_pack=get_voice_pack,
    get_volume=get_voice_volume,
    get_audio_path=get_audio_path,
)

# Inizializzazione contesto unificato per identikit_profiler (Zero duplicazioni di modulo)
identikit_profiler.init_context(
    speaker=speaker,
    relay=relay,
    voice_arbiter=voice_arbiter,
    get_volume=get_voice_volume,
    get_audio_path=get_audio_path
)

def is_system_armed() -> tuple:
    """
    Verifica se il sistema è in stato ARMATO (fari e voce attivi)
    oppure in MONITORAGGIO SILENZIOSO (orario di lavoro o disarmo manuale).
    Ritorna: (is_armed: bool, ragione: str)
    """
    # Override prioritario per collaudo e test sul campo (evita silenziamenti diurni indesiderati)
    if os.environ.get("FORCE_ARMED", "false").lower() in ("true", "1", "yes"):
        return True, "Armato forzato da variabile FORCE_ARMED=true (.env)"

    cfg = _get_cached_settings()
    mode = str(os.environ.get("SENTINEL_SECURITY_MODE") or cfg.get("security_mode", "auto")).lower()

    if mode == "armed":
        return True, "Armato 24/7 (Manuale)"
    if mode == "disarmed":
        return False, "Disarmato manuale (Monitoraggio silenzioso)"

    # Modalità "auto" (pianificazione oraria)
    now = datetime.now()
    weekday = now.isoweekday() # 1=Lunedì, ..., 7=Domenica
    work_days = cfg.get("work_days", [1, 2, 3, 4, 5])

    if weekday not in work_days:
        return True, f"Armato automatico (Fine settimana - giorno {weekday})"

    start_str = cfg.get("work_start", "08:00")
    end_str = cfg.get("work_end", "18:30")
    cur_time = now.strftime("%H:%M")

    try:
        if start_str <= cur_time < end_str:
            return False, f"Pausa Lavoro ({start_str} - {end_str}, ora attuale: {cur_time})"
        else:
            return True, f"Armato automatico (Fascia Notturna {end_str} - {start_str}, ora: {cur_time})"
    except Exception as e:
        return True, f"Armato fallback ({e})"

def is_valid_human_proportions(box: list) -> bool:
    """
    Pezzettino 1: Filtro di Buonsenso per le Sagome (stile Jev / Calibrated Decision).
    Verifica se il bounding box [ymin, xmin, ymax, xmax] ha proporzioni realistiche per un essere umano:
    1. Aspect ratio: altezza / larghezza >= MIN_HUMAN_ASPECT_RATIO (default 1.2).
       Un essere umano in piedi o che cammina e' slanciato verticalmente (ratio tipico 1.8 - 2.8).
       Una sedia da ufficio, uno scatolone o un oggetto sul tavolo ha una forma quasi quadrata (ratio ~ 0.8 - 1.1).
    2. Area massima: non occupa piu' del MAX_PERSON_AREA_RATIO (default 45%) dello schermo
       (scarta oggetti giganti a ridosso dell'obiettivo sul tavolo).
    """
    if not HUMAN_RATIO_FILTER_ENABLED:
        return True
    if not box or len(box) != 4:
        return True  # Fail-safe: se le coordinate non sono disponibili non blocchiamo

    try:
        ymin, xmin, ymax, xmax = [float(c) for c in box]
        h = abs(ymax - ymin)
        w = abs(xmax - xmin)
        if w <= 0 or h <= 0:
            return True

        aspect_ratio = h / w

        # Se le coordinate sono normalizzate (0.0 - 1.0):
        if ymax <= 1.0 and xmax <= 1.0:
            area = h * w
            if area > MAX_PERSON_AREA_RATIO:
                logger.info(
                    ">>> [FILTRO SAGOMA] Oggetto scartato: occupa il %.1f%% dello schermo (> %.0f%%) a ridosso dell'obiettivo.",
                    area * 100, MAX_PERSON_AREA_RATIO * 100
                )
                return False

        if aspect_ratio < MIN_HUMAN_ASPECT_RATIO:
            logger.info(
                ">>> [FILTRO SAGOMA] Sagoma scartata: proporzioni non umane (H/W = %.2f < %.2f) - probabile sedia, scatola o riflesso.",
                aspect_ratio, MIN_HUMAN_ASPECT_RATIO
            )
            return False

        return True
    except Exception as e:
        logger.warning("Avviso calcolo proporzioni sagoma: %s", e)
        return True

# Cache di tracciamento posizioni per Pezzettino 2 (Dynamic Movement)
_track_positions = {}
_track_lock = threading.Lock()

def is_dynamic_movement(event_id: str, box: list, event_type: str) -> bool:
    """
    Pezzettino 2: Filtro di Movimento Dinamico & Traiettoria (Anti-Oggetti Statici).
    Verifica se la sagoma rilevata sta compiendo uno spostamento effettivo nell'inquadratura:
    - 'new': Primo frame di apparizione -> memorizza posizione iniziale e autorizza (priorità massima).
    - 'update': Calcola lo spostamento euclideo normalizzato del centroide del bounding box.
      Se la sagoma e' ferma (es. sedia, cappotto, scatola) o vibra leggermente sul posto (delta < MIN_MOVEMENT_DISTANCE),
      sopprime i trigger ripetuti.
    - 'end': Pulisce la memoria del tracciamento per evitare memory leak.
    """
    if not MOVEMENT_FILTER_ENABLED:
        return True
    if not event_id:
        return True

    with _track_lock:
        if event_type == "end":
            _track_positions.pop(event_id, None)
            return True

        if not box or len(box) != 4:
            return True

        try:
            ymin, xmin, ymax, xmax = [float(c) for c in box]
            cx = (xmin + xmax) / 2.0
            cy = (ymin + ymax) / 2.0
            now = time.time()

            if event_id not in _track_positions or event_type == "new":
                if len(_track_positions) > 500:
                    _track_positions.clear()
                _track_positions[event_id] = {
                    "last_center": (cx, cy),
                    "first_center": (cx, cy),
                    "first_time": now,
                    "updates_count": 0,
                    "total_movement": 0.0,
                    "triggered": False,
                }
                return True

            track = _track_positions[event_id]
            last_cx, last_cy = track["last_center"]
            first_cx, first_cy = track["first_center"]

            # Distanza istantanea dall'ultimo frame e dall'inizio
            step_distance = ((cx - last_cx) ** 2 + (cy - last_cy) ** 2) ** 0.5
            total_displacement = ((cx - first_cx) ** 2 + (cy - first_cy) ** 2) ** 0.5

            track["last_center"] = (cx, cy)
            track["updates_count"] += 1
            track["total_movement"] += step_distance

            # Se l'oggetto ha gia' prodotto un trigger e ora e' praticamente immobile:
            if track["updates_count"] >= 3 and total_displacement < MIN_MOVEMENT_DISTANCE:
                logger.debug(
                    ">>> [FILTRO MOVIMENTO] Sagoma '%s' statica (spostamento totale %.3f < %.3f): trigger soppresso.",
                    event_id[:8], total_displacement, MIN_MOVEMENT_DISTANCE
                )
                return False

            return True
        except Exception as e:
            logger.warning("Avviso calcolo movimento dinamico: %s", e)
            return True

def trigger_person_deterrence(camera: str, zone: str = None, event_timestamp: float = None, persons: int = 1):
    """
    Trigger immediato deterrenza (Faretto + Voce Fanvil):
    1. Riflesso vocale immediato (Livello 0) senza attendere socket Modbus ne' cloud.
    2. Turno vocale concesso dal VoiceArbiter (cooldown locale per zona + globale anti-eco
       su più camere), separato dal turno della frase di ORIN che seguira'.
    3. Cronometro latenza software stampato nei log per verifica oggettiva dei millisecondi.
    4. Accensione faretto in thread separato per azzerare contese socket su MQTT loop.
    """
    now = time.time()
    loc_key = zone if zone else camera

    # Calcolo cronometro latenza software
    latency_str = ""
    if event_timestamp:
        try:
            latency_ms = (now - float(event_timestamp)) * 1000.0
            latency_str = f" [Latenza software: {latency_ms:.1f}ms]"
        except Exception:
            pass

    # 0. Verifica stato di Armamento (Orario di lavoro / Fascia notturna / Disarmo manuale)
    is_armed, arm_reason = is_system_armed()
    if not is_armed:
        logger.info(
            ">>> [MONITORAGGIO SILENZIOSO] Rilevamento su '%s' [loc: %s] soppresso: %s",
            camera, loc_key, arm_reason
        )
        return False

    # 1. Voce immediata. Il turno concesso qui apre anche la finestra in cui la frase
    #    contestuale di ORIN avra' sempre la parola (vedi voice_arbiter.py).
    try:
        from orin_brain import orin_brain
        orin_active = orin_brain.is_active()
    except Exception:
        orin_active = False

    voiced_now = REFLEX_ENABLED or not orin_active
    if voice_arbiter.claim_reflex(camera, loc_key, voiced=voiced_now):
        if REFLEX_ENABLED:
            logger.info(">>> AZIONE IMMEDIATA: riflesso vocale per '%s' [loc: %s]%s", camera, loc_key, latency_str)
            reflex.fire(camera, persons=persons)
        elif not orin_active:
            audio_file = get_audio_path("03_avviso_dissuasione")
            volume = get_voice_volume()
            logger.info(
                ">>> AZIONE IMMEDIATA AUDIO (FALLBACK LOCALE): Riproduzione avviso vocale '%s' per '%s' [loc: %s]%s (multicast RTP %s:%d, volume %.0f%%)",
                os.path.basename(audio_file), camera, loc_key, latency_str, FANVIL_MULTICAST_IP, FANVIL_MULTICAST_PORT, volume
            )
            speaker.play_audio_file(audio_file, volume_percent=volume, priority=Priority.REFLEX)
        else:
            logger.info(
                ">>> [ORIN ACTIVE] Rilevamento su '%s' [loc: %s]%s: riflesso disattivato, la voce sara' quella contestuale di ORIN",
                camera, loc_key, latency_str
            )

    # 2. Accensione Fari LED integrati Reolink (Spotlight) + opzionale Relè
    if not is_in_cooldown(f"{loc_key}_faro", cooldown_seconds=5.0):
        # A. Fari LED bianchi integrati Reolink (senza fili o relè esterni)
        if USE_REOLINK_SPOTLIGHT:
            reolink_spotlight.trigger_spotlight(camera, duration_seconds=FARETTO_DURATION)

        # B. Relè esterno (attivato solo se USE_EXTERNAL_RELAY_LIGHT=true)
        if USE_EXTERNAL_RELAY_LIGHT:
            relay_channel = CAMERA_RELAY_MAP.get(camera, RELAY_CHANNEL_PIAZZALE)
            logger.info(">>> AZIONE FARETTO RELÈ: Persona su '%s' [loc: %s] -> Relè Ch %d per %ds", camera, loc_key, relay_channel + 1, int(FARETTO_DURATION))
            threading.Thread(
                target=relay.accendi_faretto,
                kwargs={"channel": relay_channel, "durata_secondi": FARETTO_DURATION},
                name="RelayFarettoTrigger",
                daemon=True
            ).start()
    return True

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

    # Scenario A: RILEVAMENTO PERSONA (Piazzale, Magazzino o Corridoio)
    if label == "person":
        if event_type in ("new", "update"):
            box = after.get("box", [])
            score = after.get("score", 0.0)

            # Pezzettino 1: verifica che la sagoma abbia proporzioni umane (scarta sedie sul tavolo)
            if not is_valid_human_proportions(box):
                return

            # Pezzettino 2: verifica che la sagoma compia un movimento dinamico effettivo (scarta oggetti statici)
            if not is_dynamic_movement(event_id, box, event_type):
                return

            # Integrazione JEV Decider: valutazione contestuale auto-adattiva per l'ambiente della telecamera
            is_threat, jev_reason, final_conf = jev_decider.evaluate_threat(
                camera=camera,
                label=label,
                box=box,
                score=score,
                displacement=0.03
            )
            if not is_threat:
                return

            event_time = after.get("start_time") or after.get("frame_time")
            # Attivazione deterrenza (faro Reolink + voce) in base a orario e stato armato
            deterrence_fired = trigger_person_deterrence(camera, zone=active_zone, event_timestamp=event_time)

            # Generazione automatica Scheda Identikit Forense
            try:
                is_armed_now, _ = is_system_armed()
                status_eval = "MINACCIA CONFERMATA — AZIONE DISSUASIONE ESEGUITA" if deterrence_fired else "TRANSITO IN MONITORAGGIO SILENZIOSO (Pausa Lavoro / Disarmato)"
                profile = identikit_profiler.generate_profile(
                    event_id=event_id,
                    camera=camera,
                    label=label,
                    score=score,
                    box=box,
                    snapshot_url=f"/api/events/{event_id}/snapshot.jpg",
                    status_evaluation=status_eval,
                    is_armed=is_armed_now
                )
                # Pubblicazione MQTT topic dedicato per aggiornamento Dashboard
                global _active_mqtt_client
                if _active_mqtt_client and _active_mqtt_client.is_connected():
                    _active_mqtt_client.publish("sentinel/identikit", json.dumps(profile), qos=0)
            except Exception as e:
                logger.warning("Avviso generazione/pubblicazione identikit: %s", e)

            # 3. Archiviazione Snapshot sul NAS (una sola volta per ID evento, istantanea)
            if has_snapshot and mark_snapshot_archived(event_id):
                nas.archive_snapshot(event_id=event_id, camera=camera, label=label)

        elif event_type == "end":
            # Pulizia tracciamento movimento dinamico per questo evento
            is_dynamic_movement(event_id, [], "end")

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
    camera = lpr_data.get("camera", "piazzale")

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
    # Nuove zone del magazzino fisico
    "zona_entrata_magazzino": "piazzale",
    "zona_parcheggio_auto": "piazzale",
    "zona_stoccaggio_merci": "magazzino",
    "zona_transito_corridoio": "corridoio",
    # Mappatura telecamere dirette
    "piazzale": "piazzale",
    "magazzino": "magazzino",
    "corridoio": "corridoio",
    # Alias retrocompatibilità
    "zona_transito_pedoni": "corridoio",
    "zona_accesso_veicoli": "piazzale",
    "zona_parcheggio": "piazzale",
    "zona_perimetro": "piazzale",
    "varco_pedonale": "magazzino",
    "varco_carrabile": "piazzale",
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
    persons = 1
    if clean_val in ("ON", "TRUE", "ACTIVE"):
        is_active = True
    else:
        try:
            count = float(clean_val)
            is_active = count > 0
            persons = max(1, int(count))
        except ValueError:
            pass

    if is_active:
        cam_name = ZONE_CAMERA_MAP.get(target, target)
        if not HUMAN_RATIO_FILTER_ENABLED:
            logger.info(
                ">>> TRIGGER IMMEDIATO PERSONA: intercettato topic '%s' (payload: '%s') -> telecamera '%s' [loc: %s]",
                topic, payload_str, cam_name, target
            )
            trigger_person_deterrence(cam_name, zone=target, persons=persons)
        else:
            # Con il filtro proporzioni umane attivo, il trigger audio viene convalidato da frigate/events
            # che possiede le coordinate spaziali del bounding box (box) per scartare sedie e forme quadrate.
            logger.debug("Notifica rapida '%s' ricevuta: convalida sagoma delegata a frigate/events", topic)

def handle_frigate_review(review_data: dict):
    """
    Riceve gli eventi aggregati da 'frigate/reviews' per fini di audit e telemetria.
    NOTA FONDAMENTALE: La deterrenza fisica (fari LED Reolink e audio Fanvil)
    è affidata in via ESCLUSIVA a 'handle_frigate_event' (topic 'frigate/events'),
    che possiede la telecamera esatta, il bounding box, il filtro proporzioni umane
    e la valutazione contestuale JEV Decider.
    Rimuovere l'attivazione attuatori da questo callback elimina il bug dell'accensione
    involontaria dei fari di altre telecamere.
    """
    if not isinstance(review_data, dict):
        return
    after = review_data.get("after", {})
    if not after:
        return
    camera = after.get("camera", "unknown")
    severity = after.get("severity", "")
    data = after.get("data", {})
    objects = data.get("objects", [])
    if "person" in objects or severity == "alert":
        logger.debug("Frigate review aggregato su '%s' (severity: %s, objects: %s)", camera, severity, objects)

def handle_dashboard_command(topic: str, data: dict):
    """Gestisce i comandi manuali dalla Dashboard (instradati centralmente su AudioBus in thread separato)."""
    try:
        if topic == "sentinel/cmd/speaker/play":
            path = data.get("path")
            volume = float(data.get("volume", 80.0))
            sound_id = data.get("sound_id", "03_avviso_dissuasione")
            audio_file = path if path and os.path.exists(path) else get_audio_path(sound_id)
            logger.info(">>> [COMANDO DASHBOARD] Riproduzione audio manuale '%s' (vol: %.0f%%) via AudioBus", os.path.basename(audio_file), volume)
            speaker.play_audio_file(audio_file, volume_percent=volume, priority=Priority.ALARM)
        elif topic == "sentinel/cmd/speaker/speak":
            text = str(data.get("text", "")).strip()
            voice = str(data.get("voice", "carmelo")).lower()
            volume = float(data.get("volume", 80.0))
            if text:
                logger.info(">>> [COMANDO DASHBOARD] Sintesi vocale manuale '%s' (vol: %.0f%%) via ORIN (async)", text[:30], volume)
                def _bg_speak():
                    try:
                        from orin_brain import orin_brain
                        orin_brain.speak(text=text, voice_pack=voice, volume_percent=volume)
                    except Exception as be:
                        logger.warning("Errore sintesi manuale dashboard: %s", be)
                threading.Thread(target=_bg_speak, name="DashboardManualSpeak", daemon=True).start()
    except Exception as e:
        logger.warning("Errore elaborazione comando dashboard: %s", e)

# ──────────────────────────────────────────────────────────────────────────────
# 5. CALLBACK MQTT
# ──────────────────────────────────────────────────────────────────────────────
_active_mqtt_client = None

def on_connect(client, userdata, flags, reason_code, properties):
    global _active_mqtt_client
    _active_mqtt_client = client
    identikit_profiler.mqtt_client = client
    if not reason_code.is_failure:
        logger.info("Connessione stabilita con successo al broker MQTT (%s:%d)", MQTT_HOST, MQTT_PORT)
        client.subscribe([("frigate/#", 0), ("sentinel/cmd/#", 0)])
        logger.info("Sentinel AI Orchestrator attivo su 'frigate/#' e 'sentinel/cmd/#' — decision engine operativo.")
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

        try:
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
                elif topic.startswith("sentinel/cmd/"):
                    handle_dashboard_command(topic, parsed_json)

            else:
                record["type"] = "text"
                record["payload"] = text_payload

                # CONTROLLO TOPIC AUDIO RAPIDI (es. frigate/<cam>/audio/scream ON)
                if "/audio/" in topic and any(alarm in topic for alarm in ("scream", "yell", "fire_alarm")):
                    handle_audio_alarm(topic, text_payload)

                # TRIGGER ISTANTANEO PERSONA (camera o zona, conteggio numerico o ON/OFF)
                elif topic.startswith("frigate/") and "/person" in topic:
                    handle_rapid_person_topic(topic, text_payload)

        except Exception as err:
            logger.error("Errore imprevisto elaborazione messaggio MQTT su topic '%s': %s", topic, err, exc_info=True)

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
    logger.info(
        "Voce: Riflesso L0 %s | cooldown riflesso locale %ds, globale %ds | pensiero ORIN su turno separato",
        "ATTIVO" if REFLEX_ENABLED else "DISATTIVATO", int(AUDIO_COOLDOWN), int(SPEAKER_GLOBAL_COOLDOWN)
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
        from gemini_live_engine import gemini_live_engine
        gemini_live_engine.start()
    except Exception as ge:
        logger.info("Gemini Live non attivo o differito: %s", ge)

    try:
        client.loop_forever(retry_first_connection=True)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Arresto orchestratore...")
        try:
            from gemini_live_engine import gemini_live_engine
            gemini_live_engine.stop()
        except Exception:
            pass
        client.disconnect()
        logger.info("Orchestratore arrestato.")

if __name__ == "__main__":
    main()
