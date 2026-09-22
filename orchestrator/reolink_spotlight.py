#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Driver Fari Integrati Reolink (Spotlight LED)

Consente a Sentinel AI di comandare l'accensione e lo spegnimento dei potenti
fari LED a luce bianca integrati nelle telecamere Reolink (es. RLC-811A),
sostituendo il vecchio faretto esterno su relè Waveshare.

Vantaggi:
- Zero hardware esterno aggiuntivo (elimina scheda relè, cavi a 220V e alimentatori).
- Illuminazione mirata: si accende solo il faro della telecamera dove si trova l'intruso.
- Asincrono e non bloccante: le chiamate HTTP viaggiano in thread separati senza
  rallentare la dissuasione vocale Fanvil.
- Anti-sfarfallio: se arrivano rilevamenti consecutivi, il timer di accensione viene
  automaticamente esteso senza interruzioni.
"""

import os
import time
import json
import logging
import threading
import urllib.request
import urllib.error

logger = logging.getLogger("SentinelReolinkSpotlight")

# Mappatura IP certificata per l'ambiente reale
DEFAULT_CAMERA_IPS = {
    "piazzale": os.environ.get("CAM_PIAZZALE_IP", "192.168.1.22"),
    "magazzino": os.environ.get("CAM_MAGAZZINO_IP", "192.168.1.20"),
    "corridoio": os.environ.get("CAM_CORRIDOIO_IP", "192.168.1.21"),
}

class ReolinkSpotlightController:
    """Controller HTTP per i fari LED a luce bianca delle telecamere Reolink."""

    def __init__(self):
        self.enabled = os.environ.get("USE_REOLINK_SPOTLIGHT", "true").lower() in ("true", "1", "yes")
        self.username = os.environ.get("CAM_USER", "admin")
        self.password = os.environ.get("CAM_PASSWORD", "Confprov33")
        self.camera_ips = dict(DEFAULT_CAMERA_IPS)
        
        # Mappa per estensione timer (camera -> timestamp spegnimento previsto)
        self._expiration_map = {}
        self._lock = threading.Lock()

        logger.info(
            "Reolink Spotlight Controller inizializzato (Attivo: %s | Telecamere: %s)",
            self.enabled,
            ", ".join(f"{k}->{v}" for k, v in self.camera_ips.items())
        )

    def _send_cgi_command(self, ip: str, state: int) -> bool:
        """
        Invia il comando CGI Reolink SetWhiteLed via HTTP POST.
        state: 1 per accendere, 0 per spegnere.
        """
        url = f"http://{ip}/cgi-bin/api.cgi?cmd=SetWhiteLed&user={self.username}&password={self.password}"
        payload = [
            {
                "cmd": "SetWhiteLed",
                "action": 0,
                "param": {
                    "WhiteLed": {
                        "channel": 0,
                        "state": state,
                        "mode": 0
                    }
                }
            }
        ]
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    logger.debug("Reolink Spotlight %s: comando inviato con successo (state=%d)", ip, state)
                    return True
                else:
                    logger.warning("Reolink Spotlight %s: risposta HTTP anomala %d", ip, resp.status)
                    return False
        except urllib.error.URLError as e:
            logger.warning("Reolink Spotlight %s: errore di connessione (%s)", ip, e.reason)
            return False
        except Exception as e:
            logger.warning("Reolink Spotlight %s: eccezione (%s)", ip, e)
            return False

    def trigger_spotlight(self, camera: str, duration_seconds: float = 30.0):
        """
        Accende il faro LED della telecamera specificata per la durata indicata.
        Se il faro è già acceso, estende la durata senza sfarfallio.
        Eseguito in thread daemon per non rallentare l'audio o il loop principale.
        """
        if not self.enabled:
            return

        ip = self.camera_ips.get(camera)
        if not ip:
            logger.debug("Nessun IP configurato per il faro della telecamera '%s'", camera)
            return

        now = time.time()
        new_expiration = now + duration_seconds

        with self._lock:
            already_active = camera in self._expiration_map
            self._expiration_map[camera] = new_expiration

        if already_active:
            logger.info(">>> [REOLINK SPOTLIGHT] Faro '%s' (%s) già attivo: timer prolungato di %.0fs", camera, ip, duration_seconds)
            return

        # Avvia l'accensione e il ciclo di spegnimento in un thread autonomo
        threading.Thread(
            target=self._spotlight_lifecycle,
            args=(camera, ip, duration_seconds),
            name=f"Spotlight_{camera}",
            daemon=True
        ).start()

    def _spotlight_lifecycle(self, camera: str, ip: str, duration_seconds: float):
        """Ciclo di vita dell'illuminazione: accende, attende e spegne al termine."""
        logger.info(">>> [REOLINK SPOTLIGHT] ACCENSIONE FARO LED su '%s' (%s) per %.0fs", camera, ip, duration_seconds)
        self._send_cgi_command(ip, state=1)

        while True:
            time.sleep(1.0)
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
