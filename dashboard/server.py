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
import logging
import sqlite3
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger("SentinelDashboard")

PORT = int(os.environ.get("DASHBOARD_PORT", "8080"))
FRIGATE_HOST = os.environ.get("FRIGATE_HOST", "frigate")
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
    "voice_gender": "male",
    "voice_profile": "carmelo",
    "voice_pack": "carmelo",
    "active_track": "03_avviso_dissuasione",
    "voice_volume": 85,
    "siren_enabled": True,
    "faro_sec": 30,
    "gate_sec": 3,
    "client_pin": "1111",
    "admin_pin": "9999",
    "audio_target": "cameras",
    "preset": "preset1",
    "custom_message": "Attenzione: Area sotto videosorveglianza con tracciamento biometrico. Allontanarsi immediatamente."
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
        host=speaker_host, http_port=speaker_port, user=speaker_user, password=speaker_password
    )
    logger.info("[HARDWARE] FanvilSpeakerController caricato: %s:%d", speaker_host, speaker_port)
except Exception as _sp_err:
    logger.error(
        "[HARDWARE] Altoparlante Fanvil NON caricato da %s (%s): la dissuasione vocale "
        "manuale rispondera' 'non disponibile'.",
        DRIVERS_DIR, _sp_err
    )

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
    metrics["devices"]["cam1"] = check_socket("192.168.20.11", 554)
    metrics["devices"]["cam2"] = check_socket("192.168.20.12", 554)
    metrics["devices"]["cam3"] = check_socket("192.168.20.13", 554)

    return metrics

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
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        
        # API Telemetria Jetson Reale
        if parsed.path == "/api/status":
            self._send_json(get_jetson_metrics())
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
            except Exception:
                self.send_response(404)
                self.end_headers()
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
            except Exception:
                # Frigate non raggiungibile o telecamera offline: restituisce 503
                self._send_json({"connected": False, "status": "offline", "camera": cam_name}, status=503)
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
            logger.info("Comando Relè: accensione Faretto Piazzale per %ss", duration)
            if relay_controller is None:
                logger.error("Comando faretto ignorato: driver relè Modbus non caricato.")
                self._send_json({
                    "success": False, "action": "faretto", "duration": duration,
                    "error": "Driver relè Modbus non disponibile sul server"
                }, status=503)
                return
            relay_controller.accendi_faretto(channel=0, durata_secondi=duration)
            self._send_json({"success": True, "action": "faretto", "duration": duration, "relay": f"{relay_host}:{relay_port}/CH1"})
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
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        pack = cfg.get("voice_pack", cfg.get("voice_gender", "carmelo"))
                        track = cfg.get("active_track", "03_avviso_dissuasione")
                except Exception:
                    pass
            pack, audio_path = resolve_audio_path(pack, track)
            logger.info("Comando Altoparlante: dissuasione vocale '%s/%s.mp3' -> %s", pack, track, audio_path)

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

            speaker_controller.play_audio_file(audio_path)
            self._send_json({"success": True, "action": "voice", "pack": pack, "track": track})
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
    logger.info("Altoparlante Fanvil : %s:%d (driver %s)", speaker_host, speaker_port, "OK" if speaker_controller else "NON DISPONIBILE")
    logger.info("================================================================")
    server = HTTPServer(("0.0.0.0", PORT), SentinelDashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArresto Dashboard Server...")
        server.server_close()

if __name__ == "__main__":
    main()
