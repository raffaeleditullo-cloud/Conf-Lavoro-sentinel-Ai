#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Script di Test Fari Reolink Spotlight

Permette di testare istantaneamente dalla Jetson (o da qualunque macchina sulla LAN)
la connessione CGI e l'accensione/spegnimento dei faretti a luce bianca delle 3 telecamere Reolink.

Uso:
    python3 scripts/test_reolink_spotlight.py                   # Esegue test diagnostico e accende piazzale per 5s
    python3 scripts/test_reolink_spotlight.py piazzale 5       # Accende il faro di piazzale per 5 secondi
    python3 scripts/test_reolink_spotlight.py magazzino 5      # Accende il faro di magazzino per 5 secondi
    python3 scripts/test_reolink_spotlight.py corridoio 5      # Accende il faro di corridoio per 5 secondi
    python3 scripts/test_reolink_spotlight.py all 5            # Accende i fari su tutte e 3 le telecamere per 5s
"""

import os
import sys
import time

# Aggiunge orchestrator al path per importare il driver ufficiale
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "orchestrator"))

from reolink_spotlight import reolink_spotlight


def main():
    target = sys.argv[1].lower() if len(sys.argv) > 1 else "piazzale"
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

    print("=" * 70)
    print("CONF-LAVORO SENTINEL AI // TEST FARI REOLINK SPOTLIGHT")
    print(f"Utente rilevato: {reolink_spotlight.username}")
    print(f"Password rilevata: {'*' * len(reolink_spotlight.password)}")
    print(f"Mappatura IP telecamere:")
    for cam, ip in reolink_spotlight.camera_ips.items():
        print(f"   - {cam:10s} -> {ip}")
    print("=" * 70)

    print("\n[FASE 1] Interrogazione diagnostica GetWhiteLed:")
    for cam, ip in reolink_spotlight.camera_ips.items():
        res = reolink_spotlight.get_white_led_status(ip)
        if res.get("success"):
            print(f"   [OK] {cam.upper():10s} ({ip}): Raggiungibile | Stato: {res.get('status')}")
        else:
            print(f"   [ERRORE] {cam.upper():10s} ({ip}): Non risponde o errore ({res.get('error') or res})")

    print("\n[FASE 2] Invio comando accensione:")
    if target in ("all", "tutti", "tutte"):
        for cam in ("piazzale", "magazzino", "corridoio"):
            print(f"   -> Accensione faro '{cam}' ({reolink_spotlight.camera_ips.get(cam)}) per {duration}s...")
            reolink_spotlight.trigger_spotlight(cam, duration_seconds=duration)
    else:
        canon = reolink_spotlight.resolve_camera(target)
        ip = reolink_spotlight.camera_ips.get(canon)
        print(f"   -> Accensione faro '{canon}' ({ip}) per {duration}s...")
        reolink_spotlight.trigger_spotlight(canon, duration_seconds=duration)

    print(f"\nIn attesa del timer di spegnimento ({duration + 1}s)...")
    time.sleep(duration + 1.5)
    print("Ciclo completato con successo.\n")


if __name__ == "__main__":
    main()
