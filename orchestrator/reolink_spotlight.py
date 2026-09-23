#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Driver Fari Integrati Reolink (Spotlight LED)

Consente a Sentinel AI di comandare l'accensione e lo spegnimento dei potenti
fari LED a luce bianca integrati nelle telecamere Reolink (es. RLC-811A, CX410),
sostituendo il vecchio faretto esterno su relè Waveshare.

Vantaggi:
- Zero hardware esterno aggiuntivo (elimina scheda relè, cavi a 220V e alimentatori).
- Illuminazione mirata: si accende solo il faro della telecamera dove si trova l'intruso.
- Asincrono e non bloccante: le chiamate HTTP viaggiano in thread separati senza
  rallentare la dissuasione vocale Fanvil.
- Anti-sfarfallio: se arrivano rilevamenti consecutivi, il timer di accensione viene
  automaticamente esteso senza interruzioni.
- Diagnostica integrata e autodetection credenziali e IP da .env / flussi Frigate.
"""

import os
import sys
import time
import json
import logging
import threading
import urllib.request
import urllib.error

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SentinelReolinkSpotlight")

# Alias per mappare qualsiasi identificativo di telecamera
CAMERA_ALIASES = {
    "piazzale": "piazzale",
    "cam1": "piazzale",
    "telecamera 1": "piazzale",
    "telecamera1": "piazzale",
    "magazzino": "magazzino",
    "cam2": "magazzino",
    "telecamera 2": "magazzino",
    "telecamera2": "magazzino",
    "corridoio": "corridoio",
    "cam3": "corridoio",
    "telecamera 3": "corridoio",
    "telecamera3": "corridoio"
}


class ReolinkSpotlightController:
    """Controller HTTP per i fari LED a luce bianca delle telecamere Reolink."""

    def __init__(self):
        self.enabled = os.environ.get("USE_REOLINK_SPOTLIGHT", "true").lower() in ("true", "1", "yes")
        self.username, self.password = self._discover_credentials()
        self.camera_ips = self._discover_camera_ips()
        
        # Mappa per estensione timer (camera -> timestamp spegnimento previsto)
        self._expiration_map = {}
        self._lock = threading.Lock()

        logger.info(
            "Reolink Spotlight Controller inizializzato (Attivo: %s | User: %s | Telecamere: %s)",
            self.enabled,
            self.username,
            ", ".join(f"{k}->{v}" for k, v in self.camera_ips.items())
        )

        # Esegue un probe diagnostico in background all'avvio per convalidare subito gli IP
        threading.Thread(target=self._probe_all_cameras, name="SpotlightInitialProbe", daemon=True).start()

    def _discover_credentials(self) -> tuple:
        """Rileva automaticamente utente e password dalle variabili d'ambiente o dal file .env."""
        user = os.environ.get("CAM_USER") or os.environ.get("REOLINK_USER") or "admin"
        pwd = os.environ.get("CAM_PASSWORD") or os.environ.get("REOLINK_PASSWORD") or os.environ.get("CAMERA_PASSWORD")

        # Cerca negli URL RTSP o HTTP-FLV già configurati per Frigate
        if not pwd:
            for env_var in (
                "FRIGATE_CAM_PIAZZALE_MAIN_URL",
                "FRIGATE_CAM_MAGAZZINO_MAIN_URL",
                "FRIGATE_CAM_CORRIDOIO_MAIN_URL",
                "FRIGATE_CAM_PIAZZALE_SUB_URL"
            ):
                val = os.environ.get(env_var, "")
                if "rtsp://" in val and "@" in val:
                    try:
                        auth_part = val.split("rtsp://")[1].split("@")[0]
                        if ":" in auth_part:
                            u, p = auth_part.split(":", 1)
                            if u: user = u
                            if p:
                                pwd = p
                                break
                    except Exception:
                        pass
                elif "password=" in val:
                    try:
                        p = val.split("password=")[1].split("&")[0].split(" ")[0]
                        if p:
                            pwd = p
                            break
                    except Exception:
                        pass

        # Controllo fallback su file .env
        if not pwd:
            for env_path in (".env", "/app/.env", "/config/.env", "../.env"):
                if os.path.exists(env_path):
                    try:
                        with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith("CAM_PASSWORD=") or line.startswith("REOLINK_PASSWORD="):
                                    pwd = line.split("=", 1)[1].strip().strip('"').strip("'")
                                    break
                                elif "rtsp://admin:" in line:
                                    try:
                                        pwd = line.split("rtsp://admin:")[1].split("@")[0]
                                        break
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                if pwd:
                    break

        if not pwd:
            pwd = "Confprov33"

        return user, pwd

    def _discover_camera_ips(self) -> dict:
        """Determina gli IP delle telecamere da env, url o default."""
        defaults = {
            "piazzale": "192.168.1.22",
            "magazzino": "192.168.1.20",
            "corridoio": "192.168.1.21"
        }
        res = {}
        for cam, def_ip in defaults.items():
            ip = os.environ.get(f"CAM_{cam.upper()}_IP")
            if not ip:
                url = os.environ.get(f"FRIGATE_CAM_{cam.upper()}_MAIN_URL") or os.environ.get(f"FRIGATE_CAM_{cam.upper()}_SUB_URL")
                if url:
                    try:
                        if "@" in url:
                            after_at = url.split("@")[1]
                            ip = after_at.split(":")[0].split("/")[0]
                        elif "://" in url:
                            ip = url.split("://")[1].split(":")[0].split("/")[0]
                    except Exception:
                        pass
            res[cam] = ip or def_ip
        return res

    def resolve_camera(self, camera: str) -> str:
        """Risolve un nome telecamera generico nel nome canonico ('piazzale', 'magazzino', 'corridoio')."""
        if not camera:
            return "piazzale"
        cam_clean = str(camera).strip().lower()
        return CAMERA_ALIASES.get(cam_clean, cam_clean)

    def get_white_led_status(self, camera_or_ip: str) -> dict:
        """
        Interroga la telecamera con GetWhiteLed per verificare se è raggiungibile,
        se le credenziali sono corrette e quali parametri supporta.
        """
        ip = self.camera_ips.get(self.resolve_camera(camera_or_ip), camera_or_ip)
        url = f"http://{ip}/cgi-bin/api.cgi?cmd=GetWhiteLed&user={self.username}&password={self.password}"
        payload = [{"cmd": "GetWhiteLed", "action": 0, "param": {"channel": 0}}]

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                parsed = json.loads(body)
                if isinstance(parsed, list) and len(parsed) > 0:
                    item = parsed[0]
                    code = item.get("code", 0)
                    if code == 0:
                        val = item.get("value", {}).get("WhiteLed", {})
                        return {"success": True, "ip": ip, "status": val}
                    else:
                        return {"success": False, "ip": ip, "code": code, "error": item.get("error")}
                return {"success": False, "ip": ip, "raw": body}
        except Exception as e:
            return {"success": False, "ip": ip, "error": str(e)}

    def _probe_all_cameras(self):
        """Esegue una diagnostica rapida su tutte le telecamere per confermare connettività e credenziali."""
        time.sleep(1.0)
        logger.info(">>> [REOLINK SPOTLIGHT] Avvio diagnostica iniziale telecamere...")
        for name, ip in self.camera_ips.items():
            st = self.get_white_led_status(ip)
            if st.get("success"):
                logger.info(">>> [REOLINK SPOTLIGHT] Telecamera '%s' (%s): CONNESSA OK. Stato fari: %s", name, ip, st.get("status"))
            else:
                logger.warning(">>> [REOLINK SPOTLIGHT] Telecamera '%s' (%s): NON RISPONDE o credenziali errate (%s)", name, ip, st.get("error") or st)

    def _send_cgi_command(self, ip: str, state: int) -> bool:
        """
        Invia il comando CGI Reolink SetWhiteLed via HTTP POST.
        state: 1 per accendere, 0 per spegnere.
        Gestisce automaticamente i formati payload supportati dalle diverse serie firmware Reolink.
        """
        url = f"http://{ip}/cgi-bin/api.cgi?cmd=SetWhiteLed&user={self.username}&password={self.password}"

        # Tentativo 1: Standard Reolink API (state + bright)
        white_led_param = {"channel": 0, "state": state}
        if state == 1:
            white_led_param["bright"] = 100

        payload = [{"cmd": "SetWhiteLed", "action": 0, "param": {"WhiteLed": white_led_param}}]

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                body_bytes = resp.read()
                try:
                    resp_data = json.loads(body_bytes.decode("utf-8"))
                    if isinstance(resp_data, list) and len(resp_data) > 0:
                        code = resp_data[0].get("code", 0)
                        if code == 0:
                            logger.info(">>> [REOLINK SPOTLIGHT] Telecamera %s: comando state=%d ESEGUITO con successo.", ip, state)
                            return True
                        
                        logger.warning(">>> [REOLINK SPOTLIGHT] Rifiutato da %s (code=%s): %s. Provo fallback semplice...", ip, code, resp_data[0].get("error"))
                except Exception:
                    if resp.status == 200:
                        return True
        except Exception as e:
            logger.warning(">>> [REOLINK SPOTLIGHT] Tentativo 1 su %s fallito (%s). Provo fallback...", ip, e)

        # Tentativo 2: Fallback payload minimale (solo channel e state)
        payload_fallback = [{"cmd": "SetWhiteLed", "action": 0, "param": {"WhiteLed": {"channel": 0, "state": state}}}]
        try:
            req_fb = urllib.request.Request(url, data=json.dumps(payload_fallback).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req_fb, timeout=2.5) as resp:
                body_fb = json.loads(resp.read().decode("utf-8"))
                if isinstance(body_fb, list) and len(body_fb) > 0 and body_fb[0].get("code", 0) == 0:
                    logger.info(">>> [REOLINK SPOTLIGHT] Telecamera %s: fallback state=%d RIUSCITO.", ip, state)
                    return True
        except Exception as e:
            logger.error(">>> [REOLINK SPOTLIGHT] Fallback su %s fallito: %s", ip, e)

        return False

    def trigger_spotlight(self, camera: str, duration_seconds: float = 30.0) -> bool:
        """
        Accende il faro LED della telecamera specificata per la durata indicata.
        Se il faro è già acceso, estende la durata senza sfarfallio.
        Eseguito in thread daemon per non rallentare l'audio o il loop principale.
        """
        if not self.enabled:
            logger.info("Reolink Spotlight disabilitato da configurazione (USE_REOLINK_SPOTLIGHT=false)")
            return False

        canon_cam = self.resolve_camera(camera)
        ip = self.camera_ips.get(canon_cam)
        if not ip:
            logger.warning("Nessun IP configurato per il faro della telecamera '%s' (input: '%s')", canon_cam, camera)
            return False

        now = time.time()
        new_expiration = now + duration_seconds

        with self._lock:
            already_active = canon_cam in self._expiration_map
            self._expiration_map[canon_cam] = new_expiration

        if already_active:
            logger.info(">>> [REOLINK SPOTLIGHT] Faro '%s' (%s) già attivo: timer prolungato a %.0fs", canon_cam, ip, duration_seconds)
            return True

        # Avvia l'accensione e il ciclo di spegnimento in un thread autonomo
        threading.Thread(
            target=self._spotlight_lifecycle,
            args=(canon_cam, ip, duration_seconds),
            name=f"Spotlight_{canon_cam}",
            daemon=True
        ).start()
        return True

    def _spotlight_lifecycle(self, camera: str, ip: str, duration_seconds: float):
        """Ciclo di vita dell'illuminazione: accende, attende e spegne al termine."""
        logger.info(">>> [REOLINK SPOTLIGHT] ACCENSIONE FARO LED su '%s' (%s) per %.0fs", camera, ip, duration_seconds)
        self._send_cgi_command(ip, state=1)

        while True:
            time.sleep(0.5)
            now = time.time()
            with self._lock:
                expiration = self._expiration_map.get(camera, 0)
                if now >= expiration:
                    # Timer scaduto: rimuovi e spegni
                    self._expiration_map.pop(camera, None)
                    break

        logger.info(">>> [REOLINK SPOTLIGHT] SPEGNIMENTO FARO LED su '%s' (%s)", camera, ip)
        self._send_cgi_command(ip, state=0)


# Istanza singleton pronta all'uso
reolink_spotlight = ReolinkSpotlightController()


# ──────────────────────────────────────────────────────────────────────────────
# TEST RUNNER DA TERMINALE
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cam_arg = sys.argv[1] if len(sys.argv) > 1 else "piazzale"
    dur_arg = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

    print("=" * 60)
    print("TEST DIRETTO FARI REOLINK SPOTLIGHT")
    print(f"Utente: {reolink_spotlight.username} | Password mascherata: {'*' * len(reolink_spotlight.password)}")
    print(f"Telecamere mappate: {reolink_spotlight.camera_ips}")
    print("=" * 60)

    print(f"\n1. Verifica stato fari su tutte le telecamere:")
    for name, ip in reolink_spotlight.camera_ips.items():
        res = reolink_spotlight.get_white_led_status(ip)
        print(f"   - {name.upper()} ({ip}): {res}")

    print(f"\n2. Accensione test faro '{cam_arg}' per {dur_arg} secondi...")
    reolink_spotlight.trigger_spotlight(cam_arg, duration_seconds=dur_arg)

    print(f"In attesa del ciclo di spegnimento ({dur_arg + 1}s)...")
    time.sleep(dur_arg + 1.5)
    print("Test completato.")
