#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Dashboard Server (Fase 3: Web Control Hub)

Server HTTP leggero basato sulla sola libreria standard.
Serve l'interfaccia statica e le API REST per relè, eventi e whitelist targhe.

Le uniche dipendenze esterne (pymodbus, requests) sono quelle dei driver hardware
condivisi con l'orchestratore, montati a runtime su /app/drivers: vedi
dashboard/requirements.txt e il servizio 'dashboard' in docker-compose.yml.
"""

import os
import sys
import json
import time
from datetime import datetime
import socket
import logging
import sqlite3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger("SentinelDashboard")

def resolve_service_host(preferred: str, fallback: str = "127.0.0.1") -> str:
    """
    Restituisce 'preferred' se il nome e' risolvibile (rete bridge Docker), altrimenti
    'fallback'. Il servizio dashboard gira con 'network_mode: host' perche' la
    dissuasione vocale manuale diffonde audio in multicast RTP verso il Fanvil A233:
    in quella modalita' il nome 'frigate' non esiste, ma l'API interna di Frigate e'
    gia' pubblicata su 127.0.0.1:5000 dal docker-compose. Stessa logica in
    orchestrator/observer.py::resolve_service_host.
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

PORT = int(os.environ.get("DASHBOARD_PORT", "8080"))
FRIGATE_HOST = resolve_service_host(os.environ.get("FRIGATE_HOST", "frigate"))
FRIGATE_PORT = int(os.environ.get("FRIGATE_PORT", "5000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.environ.get("CONFIG_DIR", "/config" if os.path.exists("/config") else os.path.abspath(os.path.join(BASE_DIR, "..", "config")))
PLATES_FILE = os.path.join(CONFIG_DIR, "known_plates.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "system_settings.json")
DETECTOR_STATUS_FILE = os.path.join(CONFIG_DIR, "detector_status.json")

# Pacchetti audio ufficiali. In container sono montati su /app/audio da
# ./orchestrator/audio (unica copia autorevole); in sviluppo locale si usa
# dashboard/audio, la stessa cartella che il browser raggiunge via 'audio/...'.
AUDIO_DIR = os.environ.get(
    "AUDIO_DIR",
    "/app/audio" if os.path.isdir("/app/audio") else os.path.join(BASE_DIR, "audio")
)

# Database eventi di Frigate. In container e' montato in SOLA LETTURA su
# /media/frigate/db dal docker-compose; in sviluppo locale si cerca ./storage/db.
# Si verifica la CARTELLA e non il file: il database viene creato da Frigate al
# primo avvio, e distinguere "volume non montato" da "database non ancora creato"
# e' esattamente cio' che serve per diagnosticare un Archivio Evidenze vuoto.
DB_DIR = os.environ.get(
    "DB_DIR",
    "/media/frigate/db" if os.path.isdir("/media/frigate/db") else os.path.abspath(os.path.join(BASE_DIR, "..", "storage", "db"))
)
DB_PATH = os.environ.get("DB_PATH", os.path.join(DB_DIR, "frigate.db"))

# Driver hardware condivisi con l'orchestratore: montati su /app/drivers in
# container, presi da ../orchestrator in sviluppo locale.
DRIVERS_DIR = "/app/drivers" if os.path.isdir("/app/drivers") else os.path.abspath(os.path.join(BASE_DIR, "..", "orchestrator"))

DEFAULT_SETTINGS = {
    "voice_gender": "carmelo",
    "voice_profile": "carmelo",
    "voice_pack": "carmelo",
    "active_track": "03_avviso_dissuasione",
    "voice_volume": 70,
    "faro_sec": 30,
    "gate_sec": 3,
    "client_pin": "1111",
    "admin_pin": "9999",
    "preset": "preset1",
    "custom_message": "Attenzione: Area sotto videosorveglianza con tracciamento biometrico. Allontanarsi immediatamente.",
    "security_mode": "auto",
    "work_start": "08:00",
    "work_end": "18:30",
    "work_days": [1, 2, 3, 4, 5]
}

# Inizializza file targhe e impostazioni se non presenti
os.makedirs(CONFIG_DIR, exist_ok=True)
if not os.path.exists(PLATES_FILE):
    initial_plates = [
        {"plate": "FG492KS", "owner": "Ing. Rocco Di Tolla", "role": "Direzione Generale", "active": True, "date": "2026-09-08"},
        {"plate": "DA812LL", "owner": "Alessio Russo", "role": "Responsabile Impianti", "active": True, "date": "2026-09-09"}
    ]
    with open(PLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(initial_plates, f, indent=2)

if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_SETTINGS, f, indent=2)

# Inizializzazione Attuatori Hardware (Relè Modbus Waveshare & Speaker Fanvil)
relay_controller = None
speaker_controller = None

sys.path.insert(0, DRIVERS_DIR)
logger.info("Driver hardware cercati in: %s", DRIVERS_DIR)

# Parametri hardware letti fuori dai try: restano disponibili per diagnostica e
# per le risposte API anche quando il driver corrispondente non si carica.
relay_host = os.environ.get("RELAY_HOST", "192.168.1.30")
relay_port = int(os.environ.get("RELAY_PORT", "4196"))
speaker_host = os.environ.get("SPEAKER_HOST", "192.168.1.31")
speaker_port = int(os.environ.get("SPEAKER_PORT", "80"))
# Canale MULTICAST RTP su cui il Fanvil A233 e' gia' in ascolto (collaudo Alessio).
fanvil_multicast_ip = os.environ.get("FANVIL_MULTICAST_IP", "239.255.1.1")
fanvil_multicast_port = int(os.environ.get("FANVIL_MULTICAST_PORT", "5004"))
fanvil_default_volume = float(os.environ.get("FANVIL_DEFAULT_VOLUME", "70"))

try:
    from relay_controller import WaveshareRelayController
    relay_controller = WaveshareRelayController(host=relay_host, port=relay_port)
    logger.info("[HARDWARE] WaveshareRelayController caricato: %s:%d", relay_host, relay_port)
except Exception as _re_err:
    logger.error(
        "[HARDWARE] Relè Modbus NON caricato da %s (%s): i comandi Faretto e Cancello "
        "risponderanno 'non disponibile' invece di pilotare il relè.",
        DRIVERS_DIR, _re_err
    )

try:
    from speaker_controller import FanvilSpeakerController
    speaker_user = os.environ.get("SPEAKER_USER", "admin")
    speaker_password = os.environ.get("SPEAKER_PASSWORD", "admin")
    speaker_controller = FanvilSpeakerController(
        host=speaker_host, http_port=speaker_port, user=speaker_user, password=speaker_password,
        multicast_ip=fanvil_multicast_ip, multicast_port=fanvil_multicast_port,
        default_volume_percent=fanvil_default_volume
    )
    logger.info(
        "[HARDWARE] FanvilSpeakerController caricato: %s (multicast RTP rtp://%s:%d)",
        speaker_host, fanvil_multicast_ip, fanvil_multicast_port
    )
except Exception as _sp_err:
    logger.error(
        "[HARDWARE] Altoparlante Fanvil NON caricato da %s (%s): la dissuasione vocale "
        "manuale rispondera' 'non disponibile'.",
        DRIVERS_DIR, _sp_err
    )

reolink_spotlight = None
try:
    from reolink_spotlight import reolink_spotlight as _reolink_spotlight
    reolink_spotlight = _reolink_spotlight
except Exception:
    pass

def _resolve_mqtt_host() -> str:
    """
    Host del broker MQTT. Con 'network_mode: host' il nome del container ('mosquitto')
    non e' risolvibile: si ripiega su 127.0.0.1, dove la porta 1883 e' gia' pubblicata
    (stesso criterio di resolve_service_host() nell'orchestratore).
    """
    preferred = os.environ.get("FRIGATE_MQTT_HOST", os.environ.get("MQTT_HOST", "127.0.0.1"))
    try:
        socket.getaddrinfo(preferred, None)
        return preferred
    except socket.gaierror:
        return "127.0.0.1"

def send_orchestrator_cmd(topic: str, payload: dict) -> bool:
    """Invia comandi vocali all'Orchestratore via MQTT per usare l'AudioBus centralizzato."""
    try:
        import paho.mqtt.publish as publish
        mqtt_host = _resolve_mqtt_host()
        mqtt_port = int(os.environ.get("FRIGATE_MQTT_PORT", os.environ.get("MQTT_PORT", "1883")))
        mqtt_user = os.environ.get("FRIGATE_MQTT_USER", "sentinel")
        mqtt_pass = os.environ.get("FRIGATE_MQTT_PASSWORD", "")
        auth = {"username": mqtt_user, "password": mqtt_pass} if mqtt_pass else None
        publish.single(topic, json.dumps(payload), hostname=mqtt_host, port=mqtt_port, auth=auth)
        logger.info("[MQTT CMD] Inoltrato comando autenticato a orchestrator su '%s'", topic)
        return True
    except Exception as e:
        # WARNING e non debug: con il ripiego la dashboard suona in proprio e puo'
        # sovrapporsi ai riflessi dell'orchestratore, quindi deve essere visibile nei log.
        logger.warning("[MQTT CMD] Comando non inoltrato all'orchestratore (%s): uso il driver locale", e)
        return False

def get_jetson_metrics():
    """Legge la telemetria reale da sysfs, /proc/meminfo e /proc/uptime su Jetson Orin Nano."""
    metrics = {
        "status": "online",
        "temperature": 61.0,
        "ram_used_mb": 4566,
        "ram_total_mb": 7600,
        "ram_free_mb": 3034,
        "swap_used_mb": 4,
        "swap_total_mb": 3800,
        "power_watts": 16.0,
        "uptime": "1h 35m",
        "devices": {
            "cam1": False,
            "cam2": False,
            "cam3": False,
            "relay_modbus": False,
            "nas_ugreen": False
        }
    }

    # 1. Temperatura SoC Tegra Orin Nano
    thermal_paths = [
        "/sys/devices/virtual/thermal/thermal_zone0/temp",
        "/sys/class/thermal/thermal_zone0/temp"
    ]
    for tp in thermal_paths:
        if os.path.exists(tp):
            try:
                with open(tp, "r") as f:
                    val = float(f.read().strip())
                    metrics["temperature"] = round(val / 1000.0 if val > 1000 else val, 1)
                    break
            except Exception:
                pass

    # 2. RAM e Swap NVMe reale da /proc/meminfo
    if os.path.exists("/proc/meminfo"):
        try:
            mem = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val_str = parts[1].strip().split()[0]
                        if val_str.isdigit():
                            mem[key] = int(val_str)
            tot_ram = mem.get("MemTotal", 0)
            avail_ram = mem.get("MemAvailable", mem.get("MemFree", 0))
            if tot_ram > 0:
                metrics["ram_total_mb"] = round(tot_ram / 1024)
                metrics["ram_free_mb"] = round(avail_ram / 1024)
                metrics["ram_used_mb"] = round((tot_ram - avail_ram) / 1024)
            tot_swap = mem.get("SwapTotal", 0)
            free_swap = mem.get("SwapFree", 0)
            if tot_swap > 0:
                metrics["swap_total_mb"] = round(tot_swap / 1024)
                metrics["swap_used_mb"] = round((tot_swap - free_swap) / 1024)
        except Exception:
            pass

    # 3. Potenza Assorbita INA3221
    power_paths = [
        "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon1/power1_input",
        "/sys/bus/i2c/drivers/ina3221x/1-0040/iio:device0/in_power0_input",
        "/sys/devices/platform/bus@0/c250000.i2c/i2c-1/1-0040/hwmon/hwmon1/power1_input"
    ]
    for pp in power_paths:
        if os.path.exists(pp):
            try:
                with open(pp, "r") as f:
                    pval = float(f.read().strip())
                    metrics["power_watts"] = round(pval / 1000000.0 if pval > 1000 else pval, 1)
                    break
            except Exception:
                pass

    # 4. Uptime di sistema da /proc/uptime
    if os.path.exists("/proc/uptime"):
        try:
            with open("/proc/uptime", "r") as f:
                up_sec = float(f.read().split()[0])
                hours = int(up_sec // 3600)
                mins = int((up_sec % 3600) // 60)
                if hours >= 24:
                    metrics["uptime"] = f"{hours // 24}d {hours % 24}h {mins}m"
                else:
                    metrics["uptime"] = f"{hours}h {mins}m"
        except Exception:
            pass

    # 5. Socket check veloce periferiche hardware (timeout 0.2s)
    import socket
    def check_socket(h, p):
        try:
            s = socket.create_connection((h, p), timeout=0.2)
            s.close()
            return True
        except Exception:
            return False

    metrics["devices"]["relay_modbus"] = check_socket(os.environ.get("RELAY_HOST", "192.168.1.30"), int(os.environ.get("RELAY_PORT", "4196")))
    metrics["devices"]["nas_ugreen"] = check_socket(os.environ.get("NAS_IP", "192.168.1.11"), 445)
    metrics["devices"]["cam1"] = check_socket(os.environ.get("CAM_PIAZZALE_IP", "192.168.1.22"), 554)
    metrics["devices"]["cam2"] = check_socket(os.environ.get("CAM_MAGAZZINO_IP", "192.168.1.20"), 554)
    metrics["devices"]["cam3"] = check_socket(os.environ.get("CAM_CORRIDOIO_IP", "192.168.1.21"), 554)

    return metrics

LOGS_DIR = os.environ.get("LOG_DIR", "/app/logs" if os.path.isdir("/app/logs") else os.path.abspath(os.path.join(BASE_DIR, "..", "storage", "logs")))

def read_recent_identikits(limit=15):
    """Legge le schede identikit forensi generate da identikit_profiler.py."""
    if not os.path.isdir(LOGS_DIR):
        return []
    cards = []
    try:
        files = [f for f in os.listdir(LOGS_DIR) if f.startswith("identikit_") and f.endswith(".json")]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(LOGS_DIR, x)), reverse=True)
        for fname in files[:limit]:
            fpath = os.path.join(LOGS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    cards.append(json.load(f))
            except Exception:
                pass
    except Exception as e:
        logger.debug("Errore lettura identikit: %s", e)
    return cards

def resolve_audio_path(pack, track):
    """
    Risolve il percorso assoluto di una traccia MP3 dentro AUDIO_DIR.

    Normalizza i nomi storici del pacchetto vocale ('male'/'female' usati dalle
    prime versioni delle impostazioni) sui nomi ufficiali 'carmelo'/'sami', con
    la stessa logica di orchestrator/observer.py::get_voice_pack, e ripiega su
    'carmelo' se la cartella del pacchetto richiesto non esiste.
    """
    normalized = str(pack or "carmelo").lower()
    if normalized in ("male", "carmelo"):
        normalized = "carmelo"
    elif normalized in ("female", "sami"):
        normalized = "sami"

    pack_dir = os.path.join(AUDIO_DIR, normalized)
    if not os.path.isdir(pack_dir):
        logger.warning(
            "Pacchetto vocale '%s' non trovato in %s: ripiego su 'carmelo'.",
            normalized, AUDIO_DIR
        )
        normalized = "carmelo"
        pack_dir = os.path.join(AUDIO_DIR, normalized)

    return normalized, os.path.join(pack_dir, f"{track}.mp3")


def _resolve_event_score(row_map):
    """
    Estrae il punteggio di confidenza di un evento Frigate.

    'top_score' e' la colonna storica, deprecata nelle versioni recenti dove il
    punteggio vive nel campo JSON 'data'. Si prova nell'ordine: top_score, poi
    data.top_score, poi data.score. Se nessuno e' disponibile si restituisce None
    e il chiamante mostra un trattino, invece di inventare un 90% plausibile.
    """
    score = row_map.get("top_score")
    if score is not None:
        try:
            return float(score)
        except (TypeError, ValueError):
            pass

    raw_data = row_map.get("data")
    if raw_data:
        try:
            parsed = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            if isinstance(parsed, dict):
                for key in ("top_score", "score"):
                    if parsed.get(key) is not None:
                        return float(parsed[key])
        except (ValueError, TypeError) as err:
            logger.debug("Campo 'data' non interpretabile per un evento: %s", err)

    return None


def read_recent_events(limit=25):
    """
    Legge gli ultimi eventi dal database SQLite di Frigate in SOLA LETTURA.

    Frigate scrive nel database di continuo: si apre con URI 'mode=ro' per non
    contendere il lock di scrittura. Lo schema viene introspezionato con
    PRAGMA table_info perche' le colonne cambiano fra le versioni di Frigate
    (in particolare 'top_score', sostituita dal campo JSON 'data').

    Ogni condizione di errore viene loggata in modo esplicito: un Archivio
    Evidenze vuoto deve sempre avere una riga di log che ne spiega il motivo.
    """
    if not os.path.isdir(DB_DIR):
        logger.error(
            "Archivio Evidenze vuoto: la cartella del database '%s' non esiste. "
            "Il volume del database di Frigate non e' montato nel container della dashboard "
            "(atteso in docker-compose.yml: '${STORAGE_DB_PATH:-./storage/db}:/media/frigate/db:ro').",
            DB_DIR
        )
        return []

    if not os.path.exists(DB_PATH):
        logger.warning(
            "Archivio Evidenze vuoto: cartella '%s' montata correttamente ma il database "
            "'%s' non esiste ancora. Normale finche' Frigate non registra il primo evento.",
            DB_DIR, DB_PATH
        )
        return []

    conn = None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5.0)
        cursor = conn.cursor()

        # Nome della tabella: in Frigate e' 'event' al SINGOLARE (verificato sul
        # database reale del Jetson). Si mantiene il ripiego su 'events' per
        # eventuali database piu' vecchi. La scelta avviene fra due valori fissi,
        # quindi il nome puo' essere interpolato nella query senza rischi.
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cursor.fetchall()}
        if "event" in tables:
            table_name = "event"
        elif "events" in tables:
            table_name = "events"
        else:
            logger.error(
                "Archivio Evidenze vuoto: in %s non esiste ne' la tabella 'event' ne' 'events'. "
                "Tabelle presenti: %s",
                DB_PATH, ", ".join(sorted(tables)) or "(nessuna)"
            )
            return []

        cursor.execute(f"PRAGMA table_info({table_name})")
        available = {r[1] for r in cursor.fetchall()}

        required = ["id", "camera", "label", "start_time"]
        missing = [c for c in required if c not in available]
        if missing:
            logger.error(
                "Archivio Evidenze non leggibile: colonne obbligatorie assenti in '%s': %s. "
                "Colonne disponibili: %s",
                table_name, ", ".join(missing), ", ".join(sorted(available))
            )
            return []

        # 'data' e' il campo JSON che nelle versioni recenti contiene il punteggio;
        # 'top_score' resta come colonna solo nei database piu' vecchi.
        optional = [c for c in ("top_score", "data", "has_clip", "has_snapshot") if c in available]
        columns = required + optional

        cursor.execute(
            "SELECT {} FROM {} ORDER BY start_time DESC LIMIT ?".format(", ".join(columns), table_name),
            (limit,)
        )
        rows = cursor.fetchall()

        events = []
        for row in rows:
            row_map = dict(zip(columns, row))
            event_id = row_map.get("id")
            has_clip = bool(row_map.get("has_clip"))
            has_snapshot = bool(row_map.get("has_snapshot"))
            score = _resolve_event_score(row_map)

            start_time = row_map.get("start_time")
            try:
                time_label = time.strftime("%H:%M:%S", time.localtime(float(start_time)))
            except (TypeError, ValueError):
                time_label = "--:--:--"

            events.append({
                "id": event_id,
                "camera": row_map.get("camera"),
                "label": row_map.get("label"),
                "time": time_label,
                "conf": f"{int(score * 100)}%" if score is not None else None,
                "has_clip": has_clip,
                "has_snapshot": has_snapshot,
                "thumb": f"/api/events/{event_id}/snapshot.jpg" if has_snapshot else None,
                "video": f"/api/events/{event_id}/clip.mp4" if has_clip else None
            })

        if not events:
            logger.info(
                "Database '%s' leggibile ma nessun evento registrato: in attesa del primo rilevamento.",
                DB_PATH
            )
        else:
            logger.info(
                "Archivio Evidenze: %d eventi letti dalla tabella '%s' di %s",
                len(events), table_name, DB_PATH
            )

        return events

    except sqlite3.OperationalError as err:
        logger.error(
            "Errore di accesso al database eventi '%s': %s. "
            "Verificare che il volume sia montato e leggibile dal container.",
            DB_PATH, err
        )
        return []
    except sqlite3.Error as err:
        logger.error("Errore SQLite durante la lettura degli eventi da '%s': %s", DB_PATH, err)
        return []
    except Exception as err:
        logger.exception("Errore imprevisto durante la lettura degli eventi: %s", err)
        return []
    finally:
        if conn is not None:
            conn.close()


class SentinelDashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _send_json(self, data, status=200):
        try:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        
        # API Telemetria Jetson Reale
        if parsed.path == "/api/status":
            self._send_json(get_jetson_metrics())
            return

        # API Diagnostica Fari Reolink Spotlight
        elif parsed.path == "/api/spotlight/status":
            if reolink_spotlight is None:
                self._send_json({"enabled": False, "error": "Driver Reolink Spotlight non caricato"}, status=503)
                return
            results = {}
            for name, ip in reolink_spotlight.camera_ips.items():
                results[name] = reolink_spotlight.get_white_led_status(ip)
            self._send_json({
                "enabled": reolink_spotlight.enabled,
                "username": reolink_spotlight.username,
                "cameras": results
            })
            return

        # API Vitality Heartbeat TensorRT Detector (Watchdog Segnalazione Alessio)
        elif parsed.path == "/api/detector/vitality":
            vitality = {
                "healthy": True,
                "status": "standby",
                "detection_fps": 0.0,
                "inference_speed_ms": 0.0,
                "cameras_active": False,
                "alert": None
            }
            # 1. Prova prima a interrogare Frigate direttamente se attivo in locale
            try:
                import urllib.request
                req = urllib.request.Request("http://127.0.0.1:5000/api/stats")
                with urllib.request.urlopen(req, timeout=1.2) as resp:
                    fstats = json.loads(resp.read().decode("utf-8"))
                    detectors = fstats.get("detectors", {})
                    trt = detectors.get("tensorrt", {})
                    d_fps = float(fstats.get("detection_fps", trt.get("detection_fps", 0.0)))
                    inf_spd = float(trt.get("inference_speed", 0.0))
                    cams = fstats.get("cameras", {})
                    c_active = any(float(c.get("camera_fps", 0.0)) > 0.5 for c in cams.values())
                    vitality["detection_fps"] = round(d_fps, 1)
                    vitality["inference_speed_ms"] = round(inf_spd, 1)
                    vitality["cameras_active"] = c_active
                    if d_fps > 0:
                        vitality["status"] = "healthy"
                    elif c_active:
                        if os.path.exists(DETECTOR_STATUS_FILE):
                            try:
                                with open(DETECTOR_STATUS_FILE, "r", encoding="utf-8") as f:
                                    sdata = json.load(f)
                                    if sdata.get("status") == "frozen":
                                        vitality["status"] = "frozen"
                                        vitality["healthy"] = False
                                        vitality["alert"] = "RILEVAMENTO BLOCCATO"
                            except Exception:
                                pass
                        if vitality["status"] != "frozen":
                            vitality["status"] = "waiting"
                    else:
                        vitality["status"] = "standby"
                    self._send_json(vitality)
                    return
            except Exception:
                pass

            # 2. Fallback: leggi da detector_status.json scritto da observer.py
            if os.path.exists(DETECTOR_STATUS_FILE):
                try:
                    with open(DETECTOR_STATUS_FILE, "r", encoding="utf-8") as f:
                        vitality = json.load(f)
                except Exception:
                    pass

            self._send_json(vitality)
            return

        # API Lettura Targhe
        elif parsed.path == "/api/plates":
            if os.path.exists(PLATES_FILE):
                try:
                    with open(PLATES_FILE, "r", encoding="utf-8") as f:
                        plates = json.load(f)
                except Exception:
                    plates = []
            else:
                plates = []
            self._send_json(plates)
            return

        # API Lettura Impostazioni Sistema & Audio TTS
        elif parsed.path == "/api/settings":
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = DEFAULT_SETTINGS
            else:
                data = DEFAULT_SETTINGS
            self._send_json(data)
            return

        # API Eventi Reali da database SQLite Frigate (sola lettura)
        elif parsed.path == "/api/events":
            self._send_json(read_recent_events(limit=25))
            return

        # API Schede Identikit Forensi generate dall'Orchestratore JEV
        elif parsed.path == "/api/identikit":
            self._send_json(read_recent_identikits(limit=15))
            return

        # API Download File JSON Scheda Identikit Forense
        elif parsed.path.startswith("/api/identikit/") and parsed.path.endswith("/download"):
            parts = parsed.path.strip("/").split("/")
            event_id = parts[2] if len(parts) >= 3 else ""
            found_card = None
            if os.path.isdir(LOGS_DIR):
                for fname in os.listdir(LOGS_DIR):
                    if fname.startswith("identikit_") and event_id in fname and fname.endswith(".json"):
                        fpath = os.path.join(LOGS_DIR, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                found_card = f.read()
                                break
                        except Exception:
                            pass
            if not found_card:
                for card in read_recent_identikits(25):
                    if card.get("event_id") == event_id or event_id.startswith(str(card.get("event_id", ""))[:8]):
                        found_card = json.dumps(card, indent=2, ensure_ascii=False)
                        break

            if found_card:
                body = found_card.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="identikit_{event_id[:12]}.json"')
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        # API Stato di Sicurezza & Orari (Armato / Disarmato / Auto)
        elif parsed.path == "/api/security/state":
            settings = dict(DEFAULT_SETTINGS)
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        settings.update(json.load(f))
                except Exception:
                    pass
            mode = settings.get("security_mode", "auto").lower()
            now = datetime.now()
            weekday = now.isoweekday()
            work_days = settings.get("work_days", [1, 2, 3, 4, 5])
            start_str = settings.get("work_start", "08:00")
            end_str = settings.get("work_end", "18:30")
            cur_time = now.strftime("%H:%M")

            if mode == "armed":
                is_armed = True
                status_text = "Armato (24/7)"
                badge = "armed"
            elif mode == "disarmed":
                is_armed = False
                status_text = "Disarmato (Pausa Lavoro)"
                badge = "disarmed"
            else:
                if weekday not in work_days:
                    is_armed = True
                    status_text = f"Armato Auto (Fine Settimana)"
                    badge = "auto_armed"
                elif start_str <= cur_time < end_str:
                    is_armed = False
                    status_text = f"Pausa Lavoro ({start_str} - {end_str})"
                    badge = "auto_disarmed"
                else:
                    is_armed = True
                    status_text = f"Armato Auto (Fascia Notturna {end_str} - {start_str})"
                    badge = "auto_armed"

            self._send_json({
                "mode": mode,
                "is_armed": is_armed,
                "status_text": status_text,
                "badge": badge,
                "work_start": start_str,
                "work_end": end_str,
                "work_days": work_days,
                "current_time": cur_time
            })
            return

        # API Proxy Media Eventi (Snapshot e Clip MP4) da Frigate
        elif parsed.path.startswith("/api/events/") and ("/snapshot.jpg" in parsed.path or "/clip.mp4" in parsed.path):
            subpath = parsed.path.replace("/api/events/", "").strip()
            import urllib.request
            frigate_url = f"http://{FRIGATE_HOST}:{FRIGATE_PORT}/api/events/{subpath}"
            try:
                req = urllib.request.Request(frigate_url)
                with urllib.request.urlopen(req, timeout=5.0) as response:
                    c_type = response.headers.get("Content-Type", "image/jpeg" if "snapshot" in subpath else "video/mp4")
                    self.send_response(200)
                    self.send_header("Content-Type", c_type)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                return
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception:
                try:
                    self.send_response(404)
                    self.end_headers()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

        # API Proxy Singolo Frame Telecamere da Frigate (http://<FRIGATE_HOST>:<PORT>/api/<camera>/latest.jpg)
        # Usa latest.jpg invece dello stream MJPEG continuo per evitare BrokenPipeError:
        # lo stream MJPEG non termina mai, blocca il thread HTTP e causa timeout + ciclo di ricaricamento.
        # Il frontend effettua il polling periodico di latest.jpg simulando il video.
        elif parsed.path.startswith("/api/camera/"):
            # Supporta sia /api/camera/{cam} che /api/camera/{cam}/latest.jpg
            cam_path = parsed.path.replace("/api/camera/", "").strip().rstrip("/")
            if cam_path.endswith("/latest.jpg"):
                cam_name = cam_path.replace("/latest.jpg", "")
            else:
                cam_name = cam_path
            import urllib.request
            # Richiede sempre il singolo fotogramma latest.jpg da Frigate
            frigate_url = f"http://{FRIGATE_HOST}:{FRIGATE_PORT}/api/{cam_name}/latest.jpg"
            try:
                req = urllib.request.Request(frigate_url)
                # Timeout elevato: su Jetson Orin Nano Frigate puo' impiegare fino a 10s per il primo frame
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = response.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
                return
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception:
                # Frigate non raggiungibile o telecamera offline: restituisce 503
                self._send_json({"connected": False, "status": "offline", "camera": cam_name}, status=503)
                return

        # API Stato ORIN Cybernetic Brain
        elif parsed.path == "/api/orin/status":
            try:
                sys.path.insert(0, DRIVERS_DIR)
                from orin_brain import orin_brain, PRESIDENT_REF_PATH
                has_key = bool(orin_brain.api_key or os.environ.get("OPENROUTER_API_KEY"))
                eleven_active = bool(os.environ.get("ELEVENLABS_API_KEY") or os.path.exists(os.path.expanduser("~/.secrets/ElevenLabs Api.txt")))
                self._send_json({
                    "name": "ORIN",
                    "status": "online" if has_key else "standby",
                    "model": orin_brain.model,
                    "president_cached": bool(orin_brain._president_ref_b64 or os.path.exists(PRESIDENT_REF_PATH)),
                    "elevenlabs_active": eleven_active
                })
            except Exception as e:
                self._send_json({"name": "ORIN", "status": "standby", "error": str(e)})
            return

        # API Immagine Biometrica di Riferimento Presidente Roberto Capobianco
        elif parsed.path in ("/api/orin/president_photo.jpg", "/config/reference_faces/roberto_capobianco.jpg"):
            target_path = os.path.join(CONFIG_DIR, "reference_faces", "roberto_capobianco.jpg")
            if not os.path.exists(target_path):
                target_path = os.path.abspath(os.path.join(BASE_DIR, "..", "config", "reference_faces", "roberto_capobianco.jpg"))
            if os.path.exists(target_path):
                try:
                    with open(target_path, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception:
                    pass
            self.send_error(404, "Foto presidente non trovata")
            return

        # Serve i file statici normalmente
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b""

        if parsed.path == "/api/relay/faretto":
            duration = 30.0
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        duration = float(cfg.get("faro_sec", 30))
                except Exception:
                    pass
            logger.info("Comando Fari Piazzale: durata %ss", duration)

            spotlight_ok = False
            if reolink_spotlight is not None:
                spotlight_ok = reolink_spotlight.trigger_spotlight("piazzale", duration_seconds=duration)

            relay_ok = False
            if relay_controller is not None:
                try:
                    relay_controller.accendi_faretto(channel=0, durata_secondi=duration)
                    relay_ok = True
                except Exception as e:
                    logger.warning("Errore relè faretto Modbus: %s", e)

            if not spotlight_ok and not relay_ok:
                logger.error("Comando faretto fallito: nessun attuatore disponibile.")
                self._send_json({
                    "success": False, "action": "faretto", "duration": duration,
                    "error": "Nessun attuatore fari disponibile (Reolink e Relè non raggiungibili)"
                }, status=503)
                return

            self._send_json({
                "success": True, "action": "faretto", "duration": duration,
                "reolink": spotlight_ok,
                "relay": f"{relay_host}:{relay_port}/CH1" if relay_ok else None
            })
            return

        elif parsed.path.startswith("/api/spotlight/"):
            cam = parsed.path.replace("/api/spotlight/", "").strip().lower()
            duration = 10.0
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        duration = float(cfg.get("faro_sec", 10))
                except Exception:
                    pass
            if reolink_spotlight is None:
                self._send_json({"success": False, "error": "Driver Reolink Spotlight non disponibile"}, status=503)
                return

            if cam in ("all", "tutti", "tutte"):
                for c in ("piazzale", "magazzino", "corridoio"):
                    reolink_spotlight.trigger_spotlight(c, duration_seconds=duration)
                logger.info("Comando Fari Reolink: accensione su TUTTE le telecamere per %ss", duration)
                self._send_json({"success": True, "cameras": ["piazzale", "magazzino", "corridoio"], "duration": duration})
            else:
                ok = reolink_spotlight.trigger_spotlight(cam, duration_seconds=duration)
                logger.info("Comando Faro Reolink '%s': durata %ss (success: %s)", cam, duration, ok)
                self._send_json({"success": ok, "camera": cam, "duration": duration})
            return

        elif parsed.path == "/api/relay/cancello":
            duration = 3.0
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        duration = float(cfg.get("gate_sec", 3))
                except Exception:
                    pass
            logger.info("Comando Relè: impulso apertura Cancello per %ss", duration)
            if relay_controller is None:
                logger.error("Comando cancello ignorato: driver relè Modbus non caricato.")
                self._send_json({
                    "success": False, "action": "cancello", "duration": duration,
                    "error": "Driver relè Modbus non disponibile sul server"
                }, status=503)
                return
            relay_controller.apri_cancello(channel=1, impulso_secondi=duration)
            self._send_json({"success": True, "action": "cancello", "duration": duration, "relay": f"{relay_host}:{relay_port}/CH2"})
            return

        elif parsed.path == "/api/speaker/voice":
            pack = "carmelo"
            track = "03_avviso_dissuasione"
            volume = fanvil_default_volume
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        pack = cfg.get("voice_pack", cfg.get("voice_gender", "carmelo"))
                        track = cfg.get("active_track", "03_avviso_dissuasione")
                        # Cursore volume della dashboard (0-100): il driver lo converte
                        # nel filtro ffmpeg 'volume' (85 -> 0.85) per il flusso RTP.
                        volume = float(cfg.get("voice_volume", fanvil_default_volume))
                except Exception as _cfg_err:
                    logger.warning(
                        "Impostazioni vocali non leggibili (%s): uso pacchetto '%s', traccia '%s', volume %.0f%%.",
                        _cfg_err, pack, track, volume
                    )
            volume = max(0.0, min(100.0, volume))
            pack, audio_path = resolve_audio_path(pack, track)
            logger.info(
                "Comando Altoparlante: dissuasione vocale '%s/%s.mp3' -> %s | multicast RTP rtp://%s:%d | volume %.0f%%",
                pack, track, audio_path, fanvil_multicast_ip, fanvil_multicast_port, volume
            )

            # 1. Inoltro prioritario via MQTT all'AudioBus dell'orchestratore (evita sovrapposizioni)
            if send_orchestrator_cmd("sentinel/cmd/speaker/play", {
                "path": audio_path, "volume": volume, "sound_id": track, "pack": pack
            }):
                self._send_json({
                    "success": True, "action": "voice", "pack": pack, "track": track,
                    "volume": volume, "transport": "mqtt-audiobus",
                    "target": f"rtp://{fanvil_multicast_ip}:{fanvil_multicast_port}"
                })
                return

            if speaker_controller is None:
                logger.error("Comando vocale ignorato: driver altoparlante non caricato.")
                self._send_json({
                    "success": False, "action": "voice", "pack": pack, "track": track,
                    "error": "Driver altoparlante Fanvil non disponibile sul server"
                }, status=503)
                return

            if not os.path.exists(audio_path):
                logger.error("Comando vocale ignorato: file audio inesistente '%s'.", audio_path)
                self._send_json({
                    "success": False, "action": "voice", "pack": pack, "track": track,
                    "error": f"File audio non trovato: {audio_path}"
                }, status=404)
                return

            started = speaker_controller.play_audio_file(audio_path, volume_percent=volume)
            if started is False:
                # Un annuncio e' gia' in corso: il driver ammette un solo flusso RTP
                # per volta, quindi la richiesta e' stata scartata, non eseguita.
                logger.warning("Comando vocale scartato: riproduzione gia' in corso sul canale multicast.")
                self._send_json({
                    "success": False, "action": "voice", "pack": pack, "track": track,
                    "error": "Annuncio gia' in corso sull'altoparlante: attendere la fine della riproduzione"
                }, status=409)
                return

            self._send_json({
                "success": True, "action": "voice", "pack": pack, "track": track,
                "volume": volume, "transport": "multicast-rtp",
                "target": f"rtp://{fanvil_multicast_ip}:{fanvil_multicast_port}"
            })
            return

        elif parsed.path == "/api/plates":
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
                action = payload.get("action")
                plates = []
                if os.path.exists(PLATES_FILE):
                    try:
                        with open(PLATES_FILE, "r", encoding="utf-8") as f:
                            plates = json.load(f)
                    except Exception:
                        plates = []

                if action == "delete":
                    target_plate = str(payload.get("plate", "")).strip().upper()
                    plates = [p for p in plates if p.get("plate", "").upper() != target_plate]
                    logger.info("Targa rimossa da NVMe: %s", target_plate)
                elif action == "toggle":
                    target_plate = str(payload.get("plate", "")).strip().upper()
                    for p in plates:
                        if p.get("plate", "").upper() == target_plate:
                            p["active"] = not p.get("active", True)
                            logger.info("Targa %s stato attivo: %s", target_plate, p["active"])
                            break
                else:
                    target_plate = str(payload.get("plate", "")).strip().upper()
                    if target_plate:
                        plates = [p for p in plates if p.get("plate", "").upper() != target_plate]
                        payload["plate"] = target_plate
                        if "active" not in payload:
                            payload["active"] = True
                        plates.insert(0, payload)
                        logger.info("Nuova targa salvata su NVMe: %s (%s)", target_plate, payload.get("owner"))

                with open(PLATES_FILE, "w", encoding="utf-8") as f:
                    json.dump(plates, f, indent=2)
                self._send_json({"success": True, "plates": plates})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=400)
            return

        elif parsed.path == "/api/security/mode":
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                new_mode = str(data.get("mode", "auto")).lower()
                if new_mode not in ("auto", "armed", "disarmed"):
                    new_mode = "auto"
                current = dict(DEFAULT_SETTINGS)
                if os.path.exists(SETTINGS_FILE):
                    try:
                        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                            current.update(json.load(f))
                    except Exception:
                        pass
                current["security_mode"] = new_mode
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2)
                logger.info("Modalità sicurezza aggiornata a: %s", new_mode)
                self._send_json({"success": True, "mode": new_mode})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=400)
            return

        elif parsed.path == "/api/settings":
            try:
                new_settings = json.loads(body.decode("utf-8"))
                current = dict(DEFAULT_SETTINGS)
                if os.path.exists(SETTINGS_FILE):
                    try:
                        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                            current.update(json.load(f))
                    except Exception:
                        pass
                current.update(new_settings)
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2)
                logger.info("Impostazioni aggiornate: Voce=%s, Vol=%s%%", current.get("voice_gender"), current.get("voice_volume"))
                self._send_json({"success": True, "settings": current})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=400)
            return

        elif parsed.path == "/api/auth/pin":
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                pin = str(data.get("pin", "")).strip()
                settings = dict(DEFAULT_SETTINGS)
                if os.path.exists(SETTINGS_FILE):
                    try:
                        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                            settings.update(json.load(f))
                    except Exception:
                        pass
                
                admin_pin = str(settings.get("admin_pin", "9999")).strip()
                client_pin = str(settings.get("client_pin", "1111")).strip()

                if pin == admin_pin:
                    self._send_json({"success": True, "role": "maintainer", "label": "Manutentore Tecnico"})
                    return
                elif pin == client_pin:
                    self._send_json({"success": True, "role": "client", "label": "Cliente Utente"})
                    return
                else:
                    self._send_json({"success": False, "error": "PIN non valido"}, status=401)
                    return
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=400)
                return

        elif parsed.path == "/api/settings/pins":
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                new_client = str(data.get("client_pin", "")).strip()
                new_admin = str(data.get("admin_pin", "")).strip()
                settings = dict(DEFAULT_SETTINGS)
                if os.path.exists(SETTINGS_FILE):
                    try:
                        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                            settings.update(json.load(f))
                    except Exception:
                        pass
                if new_client:
                    settings["client_pin"] = new_client
                if new_admin:
                    settings["admin_pin"] = new_admin
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=2)
                self._send_json({"success": True, "message": "PIN aggiornati con successo"})
                return
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=400)
        elif parsed.path == "/api/orin/speak":
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                text = str(data.get("text", "")).strip()
                voice = str(data.get("voice", "carmelo")).lower()
                volume = float(data.get("volume", 70))
                # 1. Inoltro prioritario via MQTT all'AudioBus centralizzato
                if send_orchestrator_cmd("sentinel/cmd/speaker/speak", {
                    "text": text, "voice": voice, "volume": volume
                }):
                    self._send_json({"success": True, "spoken_text": text, "voice": voice, "transport": "mqtt-audiobus"})
                    return

                # Fallback su driver locale
                sys.path.insert(0, DRIVERS_DIR)
                from orin_brain import orin_brain
                ok = orin_brain.speak(text=text, voice_pack=voice, volume_percent=volume)
                self._send_json({"success": ok, "spoken_text": text, "voice": voice})
                return
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=400)
                return

        self.send_error(404, "Endpoint non trovato")

def main():
    logger.info("================================================================")
    logger.info("CONF-LAVORO SENTINEL AI — DASHBOARD WEB HUB (FASE 3)")
    logger.info("Interfaccia attiva su: http://0.0.0.0:%d", PORT)
    logger.info("Cartella statica    : %s", BASE_DIR)
    logger.info("Configurazione      : %s", CONFIG_DIR)
    logger.info("Pacchetti audio     : %s (esiste: %s)", AUDIO_DIR, os.path.isdir(AUDIO_DIR))
    logger.info("Database eventi     : %s (esiste: %s)", DB_PATH, os.path.exists(DB_PATH))
    logger.info("Frigate API         : http://%s:%d", FRIGATE_HOST, FRIGATE_PORT)
    logger.info("Relè Modbus         : %s:%d (driver %s)", relay_host, relay_port, "OK" if relay_controller else "NON DISPONIBILE")
    logger.info(
        "Altoparlante Fanvil : %s via multicast RTP rtp://%s:%d (driver %s)",
        speaker_host, fanvil_multicast_ip, fanvil_multicast_port,
        "OK" if speaker_controller else "NON DISPONIBILE"
    )
    logger.info("================================================================")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), SentinelDashboardHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArresto Dashboard Server...")
        server.server_close()

if __name__ == "__main__":
    main()
