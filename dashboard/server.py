#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Dashboard Server (Fase 3: Web Control Hub)
Server HTTP leggero a zero dipendenze esterne.
Serve l'interfaccia statica e le API REST per relè, eventi e whitelist targhe.
"""

import os
import sys
import json
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

PORT = int(os.environ.get("DASHBOARD_PORT", "8080"))
FRIGATE_HOST = os.environ.get("FRIGATE_HOST", "frigate")
FRIGATE_PORT = int(os.environ.get("FRIGATE_PORT", "5000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.environ.get("CONFIG_DIR", "/config" if os.path.exists("/config") else os.path.abspath(os.path.join(BASE_DIR, "..", "config")))
PLATES_FILE = os.path.join(CONFIG_DIR, "known_plates.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "system_settings.json")
DETECTOR_STATUS_FILE = os.path.join(CONFIG_DIR, "detector_status.json")

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

try:
    sys.path.insert(0, os.path.join(BASE_DIR, "..", "orchestrator"))
    from relay_controller import WaveshareRelayController
    relay_host = os.environ.get("RELAY_HOST", "192.168.1.30")
    relay_port = int(os.environ.get("RELAY_PORT", "4196"))
    relay_controller = WaveshareRelayController(host=relay_host, port=relay_port)
    print(f"[HARDWARE] WaveshareRelayController collegato: {relay_host}:{relay_port}")
except Exception as _re_err:
    print(f"[HARDWARE WARN] Relè Modbus non caricato (modalità offline): {_re_err}")

try:
    from speaker_controller import FanvilSpeakerController
    speaker_host = os.environ.get("SPEAKER_HOST", "192.168.1.31")
    speaker_port = int(os.environ.get("SPEAKER_PORT", "80"))
    speaker_controller = FanvilSpeakerController(host=speaker_host, http_port=speaker_port)
    print(f"[HARDWARE] FanvilSpeakerController collegato: {speaker_host}:{speaker_port}")
except Exception as _sp_err:
    print(f"[HARDWARE WARN] Speaker Fanvil non caricato (modalità offline): {_sp_err}")

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

        # API Eventi Reali da database SQLite Frigate
        elif parsed.path == "/api/events":
            events = []
            db_path = os.environ.get("DB_PATH", "/media/frigate/db/frigate.db" if os.path.exists("/media/frigate/db/frigate.db") else os.path.join(BASE_DIR, "..", "storage", "db", "frigate.db"))
            if os.path.exists(db_path):
                try:
                    import sqlite3
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("SELECT id, camera, label, start_time, top_score, has_clip, has_snapshot FROM events ORDER BY start_time DESC LIMIT 25")
                    rows = c.fetchall()
                    conn.close()
                    for r in rows:
                        events.append({
                            "id": r[0],
                            "camera": r[1],
                            "label": r[2],
                            "time": time.strftime("%H:%M:%S", time.localtime(r[3])),
                            "conf": f"{int(r[4] * 100)}%" if r[4] else "90%",
                            "has_clip": bool(r[5]) if len(r) > 5 else False,
                            "has_snapshot": bool(r[6]) if len(r) > 6 else False,
                            "thumb": f"/api/events/{r[0]}/snapshot.jpg" if (len(r) > 6 and r[6]) else None,
                            "video": f"/api/events/{r[0]}/clip.mp4" if (len(r) > 5 and r[5]) else None
                        })
                except Exception:
                    pass
            self._send_json(events)
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
            print(f">>> [DASHBOARD] Comando Relè: Accensione Faretto Piazzale per {duration}s")
            if relay_controller:
                relay_controller.accendi_faretto(channel=0, durata_secondi=duration)
            self._send_json({"success": True, "action": "faretto", "duration": duration, "relay": "192.168.1.30:4196/CH1"})
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
            print(f">>> [DASHBOARD] Comando Relè: Impulso Apertura Cancello per {duration}s")
            if relay_controller:
                relay_controller.apri_cancello(channel=1, impulso_secondi=duration)
            self._send_json({"success": True, "action": "cancello", "duration": duration, "relay": "192.168.1.30:4196/CH2"})
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
            audio_path = os.path.join(BASE_DIR, "..", "orchestrator", "audio", pack, f"{track}.mp3")
            print(f">>> [DASHBOARD] Comando Altoparlante: Dissuasione Vocale '{pack}/{track}.mp3'")
            if speaker_controller and os.path.exists(audio_path):
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
                    print(f">>> [DASHBOARD] Targa rimossa da NVMe: {target_plate}")
                elif action == "toggle":
                    target_plate = str(payload.get("plate", "")).strip().upper()
                    for p in plates:
                        if p.get("plate", "").upper() == target_plate:
                            p["active"] = not p.get("active", True)
                            print(f">>> [DASHBOARD] Targa {target_plate} stato attivo: {p['active']}")
                            break
                else:
                    target_plate = str(payload.get("plate", "")).strip().upper()
                    if target_plate:
                        plates = [p for p in plates if p.get("plate", "").upper() != target_plate]
                        payload["plate"] = target_plate
                        if "active" not in payload:
                            payload["active"] = True
                        plates.insert(0, payload)
                        print(f">>> [DASHBOARD] Nuova targa salvata su NVMe: {target_plate} ({payload.get('owner')})")

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
                print(f">>> [DASHBOARD] Impostazioni aggiornate: Voce={current.get('voice_gender')}, Vol={current.get('voice_volume')}%")
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
    print(f"================================================================")
    print(f"CONF-LAVORO SENTINEL AI — DASHBOARD WEB HUB (FASE 3)")
    print(f"Interfaccia attiva su: http://0.0.0.0:{PORT}")
    print(f"Cartella statica: {BASE_DIR}")
    print(f"================================================================")
    server = HTTPServer(("0.0.0.0", PORT), SentinelDashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArresto Dashboard Server...")
        server.server_close()

if __name__ == "__main__":
    main()
