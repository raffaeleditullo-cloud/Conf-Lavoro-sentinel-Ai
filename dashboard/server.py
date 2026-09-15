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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.environ.get("CONFIG_DIR", "/config" if os.path.exists("/config") else os.path.abspath(os.path.join(BASE_DIR, "..", "config")))
PLATES_FILE = os.path.join(CONFIG_DIR, "known_plates.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "system_settings.json")

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
        
        # API Telemetria Jetson
        if parsed.path == "/api/status":
            status_data = {
                "status": "online",
                "temperature": 54.8,
                "ram_used_mb": 4810,
                "ram_free_mb": 2480,
                "swap_used_mb": 180,
                "uptime": "5h 40m",
                "devices": {
                    "cameras": 3,
                    "relay_modbus": True,
                    "nas_ugreen": True
                }
            }
            self._send_json(status_data)
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
            frigate_url = f"http://127.0.0.1:5000/api/events/{subpath}"
            try:
                req = urllib.request.Request(frigate_url)
                with urllib.request.urlopen(req, timeout=3.0) as response:
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

        # API Proxy Stream Telecamere da Frigate (localhost:5000/api/<camera>)
        elif parsed.path.startswith("/api/camera/"):
            cam_name = parsed.path.replace("/api/camera/", "").strip()
            import urllib.request
            frigate_url = f"http://127.0.0.1:5000/api/{cam_name}"
            try:
                req = urllib.request.Request(frigate_url)
                with urllib.request.urlopen(req, timeout=1.5) as response:
                    content_type = response.headers.get("Content-Type", "image/jpeg")
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                return
            except Exception:
                # Telecamera o Frigate disconnessi: 503 con fallback standby
                self._send_json({"connected": False, "status": "offline", "camera": cam_name}, status=503)
                return

        # Serve i file statici normalmente
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b""

        if parsed.path == "/api/relay/faretto":
            print(">>> [DASHBOARD] Comando manuale: Accensione Faretto Piazzale")
            self._send_json({"success": True, "action": "faretto"})
            return

        elif parsed.path == "/api/relay/cancello":
            print(">>> [DASHBOARD] Comando manuale: Impulso Apertura Cancello")
            self._send_json({"success": True, "action": "cancello"})
            return

        elif parsed.path == "/api/speaker/voice":
            print(">>> [DASHBOARD] Comando manuale: Dissuasione Vocale")
            self._send_json({"success": True, "action": "voice"})
            return

        elif parsed.path == "/api/plates":
            try:
                new_plate = json.loads(body.decode("utf-8"))
                plates = []
                if os.path.exists(PLATES_FILE):
                    with open(PLATES_FILE, "r", encoding="utf-8") as f:
                        plates = json.load(f)
                plates.insert(0, new_plate)
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
