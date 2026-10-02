#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — MODULO CERVELLO CIBERNETICO: ORIN (ORIN BRAIN)
Architettura di Visione Multimodale, Riconoscimento Relazionale e Dialogo Predittivo

Proprietà intellettuale: Conf-Lavoro Sentinel AI
Regolazione cognitiva: HEXAD Cybernetic Protocol (OCULUS, CORIS, ANIMA, MNEME, DEMON, PEIRA)
Modello Vision: google/gemini-2.5-flash via OpenRouter (Zero storage persistente cloud)
"""

import os
import io
import sys
import json
import time
import base64
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("SentinelOrin")

# Configurazione API OpenRouter
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("ORIN_VISION_MODEL", "google/gemini-2.5-flash")
TIMEOUT_SECONDS = float(os.environ.get("ORIN_TIMEOUT_SECONDS", "3.5"))

# Cartella immagini di riferimento dei volti noti (es. Presidente Roberto)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FACES_DIR = os.path.join(BASE_DIR, "config", "reference_faces")
PRESIDENT_REF_PATH = os.path.join(FACES_DIR, "roberto_capobianco.jpg")


def optimize_image_for_vlm(image_bytes: bytes, max_dim: int = 512, quality: int = 75) -> str:
    """Comprime l'immagine in RAM a 512px max JPEG per abbattere i tempi di upload di rete a meno di 20ms."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(out.getvalue()).decode("utf-8")
    except Exception as e:
        logger.debug("Compressione PIL non disponibile, uso base64 raw: %s", e)
        return base64.b64encode(image_bytes).decode("utf-8")


class OrinBrain:
    """
    Cervello visivo e interattivo di Sentinel AI (ORIN).
    Analizza i fotogrammi dei varchi, comprende le azioni, riconosce il Presidente
    e genera frasi di benvenuto o deterrenza con intelligenza viva.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.model = DEFAULT_MODEL
        self._president_ref_b64 = None
        self._load_president_reference()

    def _load_president_reference(self):
        """Carica in cache l'immagine di riferimento del Presidente Roberto Capobianco se disponibile."""
        if os.path.exists(PRESIDENT_REF_PATH):
            try:
                with open(PRESIDENT_REF_PATH, "rb") as f:
                    self._president_ref_b64 = optimize_image_for_vlm(f.read(), max_dim=400, quality=70)
                logger.info(">>> [ORIN] Memoria facciale caricata e ottimizzata: Presidente Roberto Capobianco (%d b64 chars)", len(self._president_ref_b64))
            except Exception as e:
                logger.warning("Impossibile caricare foto di riferimento Presidente: %s", e)

    def _build_system_prompt(self, is_armed: bool, camera: str) -> str:
        """Costruisce il prompt HEXAD disciplinato e caloroso di ORIN."""
        return (
            "Tu sei ORIN, il copilota e custode cibernetico di Conf-Lavoro Sentinel AI.\n"
            "Sei intelligente, sveglio, educato e cordiale con le persone autorizzate, "
            "ma inflessibile e autorevole contro intrusi o comportamenti pericolosi.\n\n"
            "LINEE GUIDA RIGOROSE (HEXAD PROTOCOL):\n"
            "1. CONFRONTO VOLTO: Ti viene fornita (quando presente) una foto di riferimento del Presidente Nazionale Roberto Capobianco. "
            "Se la persona inquadrata nella telecamera corrisponde ai tratti somatici, barba/viso o portamento di Roberto, "
            "identificalo IMMEDIATAMENTE come 'Roberto Capobianco'.\n"
            "2. ACCOGLIENZA PRESIDENTE: Se è Roberto, formula un saluto caloroso, cordiale e deferente in italiano "
            "(es. 'Buongiorno Presidente Roberto! È un piacere vederla, cancello in apertura. Buona giornata di lavoro.'), "
            "e imposta 'open_gate': true.\n"
            "3. RICONOSCIMENTO AZIONI: Guarda cosa fa la persona. Ha un pacco da consegnare? È un operaio in tuta? "
            "Sta semplicemente camminando? Sta scavalcando o manomettendo una porta? C'è fumo o pericolo?\n"
            "4. ORARIO DIURNO / DIPENDENTI: Se è una persona normale che lavora o consegna merci, sii educato e accogliente.\n"
            "5. INTRUSI / SOGGETTI SOSPETTI (o notte): Sii perentorio, tagliente e fermo. Avvertilo che è inquadrato in 4K "
            "e che la sua scheda identificativa è stata inviata ai server di sicurezza.\n"
            "6. BREVITÀ: La frase parlata ('spoken_message') deve essere di MASSIMO 18-20 parole, perfetta per la voce umana di Carmelo.\n\n"
            "Rispondi ESCLUSIVAMENTE in formato JSON valido con questa struttura:\n"
            "{\n"
            '  "is_president": boolean,\n'
            '  "subject_description": "descrizione sintetica abbigliamento e tratti certi",\n'
            '  "action_detected": "cosa sta facendo esattamente",\n'
            '  "threat_level": "none" | "low" | "high",\n'
            '  "spoken_message": "la frase esatta in italiano che ORIN deve pronunciare a voce",\n'
            '  "open_gate": boolean\n'
            "}"
        )

    def analyze_frame(
        self,
        image_bytes: bytes,
        camera: str = "piazzale",
        is_armed: bool = True
    ) -> Dict[str, Any]:
        """
        Analizza un fotogramma JPEG della telecamera via OpenRouter (Gemini 2.5 Flash).
        Restituisce il verdetto analitico e il messaggio vocale generato da ORIN.
        """
        t0 = time.time()
        api_key = self.api_key or os.environ.get("OPENROUTER_API_KEY")

        if not api_key:
            logger.debug("ORIN: OPENROUTER_API_KEY non configurata, fallback nominale.")
            return self._fallback_response(is_armed, "Chiave API assente")

        try:
            target_b64 = optimize_image_for_vlm(image_bytes, max_dim=512, quality=75)

            # Costruzione dei contenuti per il modello multimodale
            content_list = []
            
            # Se abbiamo la foto di riferimento del Presidente, la alleghiamo come confronto
            if self._president_ref_b64:
                content_list.append({
                    "type": "text",
                    "text": "IMMAGINE 1: Foto di riferimento ufficiale del Presidente Roberto Capobianco."
                })
                content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{self._president_ref_b64}"}
                })

            content_list.append({
                "type": "text",
                "text": f"IMMAGINE TARGET: Telecamera '{camera}' di Conf-Lavoro Sentinel AI. Analizza il soggetto inquadrato ora:"
            })
            content_list.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{target_b64}"}
            })

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": self._build_system_prompt(is_armed, camera)
                    },
                    {
                        "role": "user",
                        "content": content_list
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "max_tokens": 250
            }

            req = urllib.request.Request(
                OPENROUTER_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://conflavoro.it",
                    "X-Title": "Conf-Lavoro Sentinel AI"
                }
            )

            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                latency_ms = round((time.time() - t0) * 1000, 1)

                raw_content = res_data["choices"][0]["message"]["content"]
                result = json.loads(raw_content)
                result["latency_ms"] = latency_ms
                result["engine"] = self.model

                logger.info(
                    ">>> [ORIN BRAIN] Elaborazione completata in %.0fms: Pres=%s | Minaccia=%s | Msg: '%s'",
                    latency_ms, result.get("is_president"), result.get("threat_level"), result.get("spoken_message")
                )
                return result

        except urllib.error.HTTPError as http_err:
            logger.warning("ORIN API HTTP Error (%d): %s", http_err.code, http_err.reason)
            return self._fallback_response(is_armed, f"HTTP Error {http_err.code}")
        except Exception as e:
            logger.warning("ORIN Vision Timeout / Errore (%.0fms): %s", (time.time() - t0) * 1000, e)
            return self._fallback_response(is_armed, str(e))

    def _fallback_response(self, is_armed: bool, reason: str) -> Dict[str, Any]:
        """Risposta fail-safe immediata locale se la rete o l'API non risponde."""
        if not is_armed:
            msg = "Buongiorno, transito in monitoraggio ordinario. Benvenuto."
            threat = "none"
        else:
            msg = "Attenzione: presenza rilevata in area riservata Conflavoro. Siete pregati di allontanarvi."
            threat = "medium"

        return {
            "is_president": False,
            "subject_description": "Soggetto rilevato da sensore ottico",
            "action_detected": "Transito varco",
            "threat_level": threat,
            "spoken_message": msg,
            "open_gate": False,
            "latency_ms": 0.0,
            "fallback": True,
            "fallback_reason": reason
        }

    def speak(
        self,
        text: str,
        voice_pack: str = "carmelo",
        volume_percent: float = 70.0,
        multicast_ip: str = "239.255.1.1",
        multicast_port: int = 5004
    ) -> bool:
        """
        Sintetizza in tempo reale il testo con ElevenLabs (voce di Carmelo o SAMI)
        e lo trasmette direttamente via stream Multicast RTP verso il Fanvil A233.
        Zero salvataggio di file MP3 su disco (zero I/O overhead).
        """
        if not text or not text.strip():
            return False

        eleven_key = os.environ.get("ELEVENLABS_API_KEY")
        if not eleven_key:
            secret_path = os.path.expanduser("~/.secrets/ElevenLabs Api.txt")
            if os.path.exists(secret_path):
                try:
                    with open(secret_path, "r", encoding="utf-8") as sf:
                        eleven_key = sf.read().strip()
                except Exception:
                    pass

        # Se non c'è la chiave ElevenLabs, usiamo il fallback offline
        if not eleven_key:
            logger.info(">>> [ORIN VOICE] ELEVENLABS_API_KEY non trovata: riproduzione traccia offline di fallback.")
            return False

        # Mappatura voci ufficiali Conflavoro
        voices = {
            "carmelo": "HuK8QKF35exsCh2e7fLT",  # Carmelo La Rosa (Autorevole, calda)
            "sami": "Ap2b3ZnSIW7h0QbBbxCq"       # Alessandra (Elegante, perentoria)
        }
        voice_id = voices.get(voice_pack.lower(), voices["carmelo"])
        tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

        vol_float = max(0.1, min(1.0, float(volume_percent) / 100.0))

        # Avvio processo FFmpeg in streaming pipe (stdin -> RTP G.711 mu-law)
        import subprocess
        import shutil
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

        cmd = [
            ffmpeg_bin,
            "-hide_banner", "-loglevel", "warning", "-nostdin",
            "-i", "pipe:0",
            "-af", f"volume={vol_float:.2f}",
            "-ac", "1",
            "-ar", "8000",
            "-acodec", "pcm_mulaw",
            "-payload_type", "0",
            "-f", "rtp",
            f"rtp://{multicast_ip}:{multicast_port}"
        ]

        try:
            logger.info(">>> [ORIN VOICE] Avvio sintesi ElevenLabs (%s) -> '%s' (vol: %.0f%%)", voice_pack, text, volume_percent)
            payload = {
                "text": text,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {
                    "stability": 0.70,
                    "similarity_boost": 0.85
                }
            }

            req = urllib.request.Request(
                tts_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "xi-api-key": eleven_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg"
                }
            )

            # Apertura FFmpeg pipe
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

            with urllib.request.urlopen(req, timeout=5.0) as resp:
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    if proc.stdin:
                        proc.stdin.write(chunk)

            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=10.0)
            logger.info(">>> [ORIN VOICE] Trasmessa con successo su Fanvil RTP %s:%d", multicast_ip, multicast_port)
            return True

        except Exception as e:
            logger.warning(">>> [ORIN VOICE] Errore streaming ElevenLabs: %s (uso fallback locale)", e)
            return False


# Istanza singleton globale
orin_brain = OrinBrain()

