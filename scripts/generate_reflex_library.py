#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Generatore della libreria del Riflesso L0

Legge le frasi da orchestrator/audio/reflex/phrases.json e, per ogni voce
(carmelo, sami), crea:
  orchestrator/audio/reflex/<voce>/<id>.ulaw    audio G.711 mu-law 8 kHz grezzo
  orchestrator/audio/reflex/<voce>/manifest.json

L'audio viene richiesto a ElevenLabs direttamente nel formato del Fanvil
(output_format=ulaw_8000): non serve ffmpeg, ne' qui ne' al momento dell'allarme.

USO
  python scripts/generate_reflex_library.py --check     verifica il formato ulaw_8000 (1 frase, 1 voce)
  python scripts/generate_reflex_library.py             genera tutte le voci
  python scripts/generate_reflex_library.py --voice carmelo --only r01_presenza r08_ancora_qui

Al termine riavviare l'orchestratore: la libreria viene caricata in RAM all'avvio.
"""

import os
import sys
import json
import time
import argparse
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_elevenlabs_voices import API_KEY, VOICES  # unica fonte di chiave e voci

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REFLEX_DIR = os.path.join(BASE_DIR, "orchestrator", "audio", "reflex")
PHRASES_FILE = os.path.join(REFLEX_DIR, "phrases.json")
# Modello multilingua: la libreria si genera una volta sola, conta la qualita' non la latenza.
MODEL_ID = "eleven_multilingual_v2"


def synthesize_ulaw(voice: str, text: str) -> bytes:
    """Richiede a ElevenLabs la frase in mu-law 8 kHz e restituisce i byte ricevuti."""
    v_info = VOICES[voice]
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{v_info['voice_id']}?output_format=ulaw_8000"
    payload = {
        "text": text,
        "model_id": MODEL_ID,
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
        headers={"xi-api-key": API_KEY, "Content-Type": "application/json", "Accept": "*/*"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return resp.read()


def is_mp3(data: bytes) -> bool:
    """True se i dati iniziano con un'intestazione ID3 (MP3): formato non atteso."""
    return data[:3] == b"ID3"


def describe_format(data: bytes) -> str:
    """Descrive il contenitore dei dati ricevuti (deve essere mu-law grezzo)."""
    if data[:4] == b"RIFF":
        return "WAV (intestazione RIFF): il generatore la rimuove, l'audio e' utilizzabile"
    if is_mp3(data):
        return "MP3: formato NON atteso, controllare output_format"
    return "mu-law grezzo (atteso). Conferma all'ascolto con: ffplay -f mulaw -ar 8000 -ac 1 <file>"


def strip_wav(data: bytes) -> bytes:
    """Rimuove un'eventuale intestazione WAV, restituendo i soli campioni."""
    if data[:4] != b"RIFF":
        return data
    pos = 12
    while pos + 8 <= len(data):
        size = int.from_bytes(data[pos + 4:pos + 8], "little")
        if data[pos:pos + 4] == b"data":
            return data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
    raise ValueError("WAV senza blocco 'data'")


def run_check() -> int:
    voice = next(iter(VOICES))
    text = "Verifica formato audio."
    print(f"Verifica output_format=ulaw_8000 con la voce '{voice}'...")
    data = synthesize_ulaw(voice, text)
    print(f"  byte ricevuti : {len(data)}")
    print(f"  primi 16 byte : {data[:16].hex(' ')}")
    print(f"  formato       : {describe_format(data)}")
    print(f"  durata stimata: {len(strip_wav(data)) / 8000.0:.2f} s (8000 byte = 1 s)")
    return 1 if is_mp3(data) else 0


def generate(voices, only) -> int:
    with open(PHRASES_FILE, "r", encoding="utf-8") as f:
        phrases = json.load(f)["clips"]
    if only:
        phrases = [p for p in phrases if p["id"] in only]

    failures = 0
    for voice in voices:
        out_dir = os.path.join(REFLEX_DIR, voice)
        os.makedirs(out_dir, exist_ok=True)
        manifest_path = os.path.join(out_dir, "manifest.json")
        manifest = {"voice": voice, "clips": []}
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

        for phrase in phrases:
            try:
                audio = strip_wav(synthesize_ulaw(voice, phrase["text"]))
                if is_mp3(audio):
                    raise ValueError("ElevenLabs ha restituito MP3 invece di mu-law")
            except (urllib.error.URLError, ValueError) as exc:
                print(f"[{voice}] {phrase['id']}: ERRORE {exc}")
                failures += 1
                continue

            file_name = f"{phrase['id']}.ulaw"
            with open(os.path.join(out_dir, file_name), "wb") as f:
                f.write(audio)
            entry = {k: v for k, v in phrase.items() if not k.startswith("_")}
            entry["file"] = file_name
            manifest["clips"] = [c for c in manifest["clips"] if c["id"] != phrase["id"]] + [entry]
            print(f"[{voice}] {phrase['id']}: {len(audio) / 8000.0:.2f} s  \"{phrase['text']}\"")
            time.sleep(0.4)

        manifest["clips"].sort(key=lambda c: c["id"])
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print(f"[{voice}] manifest aggiornato: {manifest_path}")

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera la libreria audio del Riflesso L0 (mu-law 8 kHz).")
    parser.add_argument("--check", action="store_true", help="verifica il formato ulaw_8000 con una sola frase")
    parser.add_argument("--voice", choices=sorted(VOICES), help="genera solo questa voce")
    parser.add_argument("--only", nargs="+", metavar="ID", help="genera solo le frasi indicate")
    args = parser.parse_args()

    if not API_KEY:
        print("ERRORE: chiave ELEVENLABS_API_KEY non trovata.")
        return 2
    if args.check:
        return run_check()
    return generate([args.voice] if args.voice else list(VOICES), args.only)


if __name__ == "__main__":
    sys.exit(main())
