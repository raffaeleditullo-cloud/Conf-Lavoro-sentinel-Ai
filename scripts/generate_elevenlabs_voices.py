#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Generatore Tracce Vocali Professionali con ElevenLabs

Utilizza le voci ultra-realistiche di ElevenLabs Multilingual v2:
- Carmelo: Carmelo La Rosa (ID: HuK8QKF35exsCh2e7fLT) — Voce maschile autorevole pro
- SAMI: Alessandra (ID: Ap2b3ZnSIW7h0QbBbxCq) — Voce femminile elegante e perentoria
"""

import os
import sys
import json
import time
import shutil
import urllib.request
import urllib.error

# Cerca la chiave API in vari percorsi standard
API_KEY = os.environ.get("ELEVENLABS_API_KEY")
if not API_KEY:
    secret_path = os.path.expanduser(r"~/.secrets/ElevenLabs Api.txt")
    if os.path.exists(secret_path):
        with open(secret_path, "r", encoding="utf-8") as f:
            API_KEY = f.read().strip()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ORCH_AUDIO_DIR = os.path.join(BASE_DIR, "orchestrator", "audio")
DASH_AUDIO_DIR = os.path.join(BASE_DIR, "dashboard", "audio")

TRACKS = {
    "01_accesso_consentito": "Accesso consentito. Area sottoposta a videosorveglianza attiva.",
    "02_targa_autorizzata": "Targa autorizzata. Apertura cancello in corso.",
    "03_avviso_dissuasione": "Attenzione. Area privata ad accesso controllato. Siete pregati di allontanarvi immediatamente.",
    "04_allarme_intrusione": "Allarme intrusione. Rilevata presenza non autorizzata. Segnalazione inviata alla sicurezza.",
    "05_targa_non_autorizzata": "Targa non autorizzata. Accesso negato, rivolgersi alla portineria.",
    "06_identikit_acquisito": "Attenzione. Intrusione rilevata. Sagoma e identikit biometrico registrati nei server di sicurezza. Allontanarsi immediatamente."
}

VOICES = {
    "carmelo": {
        "voice_id": "HuK8QKF35exsCh2e7fLT", # Carmelo La Rosa
        "stability": 0.72,
        "similarity_boost": 0.85
    },
    "sami": {
        "voice_id": "Ap2b3ZnSIW7h0QbBbxCq", # Alessandra
        "stability": 0.72,
        "similarity_boost": 0.85
    }
}

def generate_track(pack: str, track_id: str, text: str) -> bool:
    if not API_KEY:
        print("ERRORE: Chiave ELEVENLABS_API_KEY non trovata!")
        return False

    v_info = VOICES.get(pack)
    if not v_info:
        print(f"ERRORE: Pacchetto vocale sconosciuto: {pack}")
        return False

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{v_info['voice_id']}"
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": v_info["stability"],
            "similarity_boost": v_info["similarity_boost"],
            "style": 0.10,
            "use_speaker_boost": True
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "xi-api-key": API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = resp.read()
            out_orch = os.path.join(ORCH_AUDIO_DIR, pack, f"{track_id}.mp3")
            out_dash = os.path.join(DASH_AUDIO_DIR, pack, f"{track_id}.mp3")
            os.makedirs(os.path.dirname(out_orch), exist_ok=True)
            os.makedirs(os.path.dirname(out_dash), exist_ok=True)
            with open(out_orch, "wb") as f:
                f.write(data)
            shutil.copyfile(out_orch, out_dash)
            print(f"[{pack}] {track_id} generato con successo ({len(data)} byte)")
            return True
    except urllib.error.HTTPError as e:
        print(f"Errore HTTP ElevenLabs ({e.code}): {e.read().decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        print(f"Errore durante la generazione ({pack}/{track_id}): {e}")
        return False

def main():
    print("Avvio generazione pacchetti audio ElevenLabs Multilingual v2...")
    total = len(VOICES) * len(TRACKS)
    count = 0
    for pack in VOICES:
        for track_id, text in TRACKS.items():
            if generate_track(pack, track_id, text):
                count += 1
            time.sleep(0.4)
    print(f"\nOperazione completata: {count}/{total} tracce generate.")

if __name__ == "__main__":
    main()
