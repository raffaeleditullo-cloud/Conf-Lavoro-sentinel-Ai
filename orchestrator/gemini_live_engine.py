#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Gemini Multimodal Live Engine ("Jarvis")

Canale bidirezionale persistente Full-Duplex (WebSocket) con Google Gemini Live API:
- Riceve flussi visivi dalle telecamere (JPEG) e audio dal microfono Fanvil A233.
- Genera direttamente streaming vocale nativo ultra-realistico (bassa latenza < 300ms).
- Riconosce il Presidente Roberto Capobianco ed esegue il Tool Calling per l'apertura del cancello.
- Si integra direttamente con AudioBus (G.711 mu-law 8 kHz) e DEMON Gate.
"""

import os
import sys
import time
import json
import base64
import struct
import logging
import asyncio
import threading
from typing import Optional, Callable

from rtp_audio_bus import Priority, get_audio_bus
from ulaw_audio import linear_to_ulaw

logger = logging.getLogger("SentinelGeminiLive")

# Conversione di frequenza: Google invia PCM 24kHz 16-bit LE, Fanvil A233 richiede mu-law 8kHz
def pcm24k_to_ulaw8k(pcm_data: bytes) -> bytes:
    """Converte campioni PCM 24 kHz 16-bit signed LE in G.711 mu-law 8 kHz."""
    num_samples = len(pcm_data) // 2
    if num_samples < 3:
        return b""
    samples = struct.unpack(f"<{num_samples}h", pcm_data[:num_samples * 2])
    out = bytearray(num_samples // 3)
    idx = 0
    for i in range(0, (num_samples // 3) * 3, 3):
        avg = (samples[i] + samples[i + 1] + samples[i + 2]) // 3
        out[idx] = linear_to_ulaw(avg)
        idx += 1
    return bytes(out)


class GeminiLiveEngine:
    """Motore di interazione continua e controllo varco basato su Gemini Multimodal Live."""

    def __init__(self):
        self.api_key = self._load_api_key()
        self.model = os.environ.get("GEMINI_LIVE_MODEL", "models/gemini-3.8-live")
        self.voice = os.environ.get("GEMINI_LIVE_VOICE", "Charon")
        # Default False: evita costi per sessioni WebSocket persistenti 24/7 a vuoto. Attivabile on-demand.
        self.enabled = os.environ.get("GEMINI_LIVE_ENABLED", "false").lower() in ("true", "1", "yes")

        self._ws = None
        self._loop = None
        self._thread = None
        self._running = False
        self._connected = False
        self._lock = threading.Lock()

        # Riferimenti hardware opzionali (Relè cancello)
        self.relay_callback: Optional[Callable[[str], None]] = None

        # Carica reference del Presidente Roberto se presente
        self.president_ref_b64 = self._load_president_ref()

    def _load_api_key(self) -> str:
        """Carica la chiave da variabile d'ambiente o dal file protetto su disco."""
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if key:
            return key
        secrets_path = os.path.expanduser(r"~/.secrets/Gemini Live API - ORIN/gemini live api.txt")
        if os.path.exists(secrets_path):
            try:
                with open(secrets_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.warning("Impossibile leggere segreto Gemini Live: %s", e)
        return ""

    def _load_president_ref(self) -> Optional[str]:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        ref_path = os.path.join(base_dir, "config", "reference_faces", "roberto_capobianco.jpg")
        if os.path.exists(ref_path):
            try:
                with open(ref_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
        return None

    def is_active(self) -> bool:
        """True se il motore è attivo, configurato e connesso al WebSocket."""
        return self.enabled and bool(self.api_key) and self._connected

    def start(self):
        """Avvia il thread in background per la sessione Live permanente."""
        if not self.enabled or not self.api_key:
            logger.info("Gemini Live non abilitato o chiave mancante. Motore in standby.")
            return

        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_event_loop, name="GeminiLiveWorker", daemon=True)
            self._thread.start()
            logger.info(">>> [GEMINI LIVE ENGINE] Avvio worker bidirezionale (Modello: %s, Voce: %s)", self.model, self.voice)

    def stop(self):
        """Ferma la sessione e chiude il socket in modo pulito."""
        with self._lock:
            self._running = False
            self._connected = False
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_event_loop(self):
        """Loop asincrono isolato in un thread dedicato."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connection_manager())

    async def _connection_manager(self):
        """Gestisce connessione, heartbeat e riconnessione automatica in caso di caduta linea."""
        import websockets

        url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={self.api_key}"

        while self._running:
            try:
                logger.info(">>> [GEMINI LIVE] Connessione al WebSocket di Google in corso...")
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    self._ws = ws
                    # 1. Configurazione Iniziale della Sessione
                    setup_payload = self._build_setup_message()
                    await ws.send(json.dumps(setup_payload))
                    ack = await ws.recv()
                    ack_data = json.loads(ack)

                    if "setupComplete" in ack_data:
                        self._connected = True
                        logger.info(">>> [GEMINI LIVE] Sessione attiva e stabilita con successo!")
                    else:
                        logger.warning(">>> [GEMINI LIVE] Risposta inattesa al setup: %s", ack)

                    # 2. Ricezione continua messaggi
                    await self._receive_loop(ws)

            except Exception as e:
                self._connected = False
                logger.warning(">>> [GEMINI LIVE] Connessione interrotta o errore rete: %s (Riconnessione tra 5s...)", e)
                await asyncio.sleep(5.0)

    def _build_setup_message(self) -> dict:
        """Costruisce il payload di inizializzazione con personalità, voce e Tool Calling del cancello."""
        system_prompt = (
            "Sei Sentinel, la sentinella cibernetica di Conf-Lavoro Sentinel AI, intelligenza vigile a guardia del varco aziendale.\n\n"
            "REGOLE DI COMPORTAMENTO (STILE JARVIS):\n"
            "1. RICONOSCIMENTO PRESIDENTE: Se riconosci il Presidente Nazionale Roberto Capobianco (viso, barba, portamento) o se si presenta a voce, "
            "salutalo con cordialità, calore e deferenza, ed esegui IMMEDIATAMENTE la funzione 'apri_cancello'.\n"
            "2. PRESENZA INTELLIGENTE E SILENZIO: Non parlare a vanvera. Se vedi una persona autorizzata o dipendente che sta semplicemente "
            "camminando o lavorando pacificamente, RIMANI IN SILENZIO e vigila con attenzione senza interromperlo continuamente. "
            "Intervieni con la voce solo quando è necessario, se ti parlano direttamente, o in caso di anomalia.\n"
            "3. INTRUSI E MINACCE: Se noti persone sospette, mascherate o tentativi di scavalcare il varco, sii perentorio, "
            "autorevole e tagliente. Intima l'alt immediato avvisando che l'area è protetta in tempo reale.\n"
            "4. LINGUA: Rispondi sempre e solo in un italiano impeccabile, naturale e fluido."
        )

        return {
            "setup": {
                "model": self.model,
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": self.voice
                            }
                        }
                    }
                },
                "systemInstruction": {
                    "parts": [{"text": system_prompt}]
                },
                "tools": [{
                    "functionDeclarations": [{
                        "name": "apri_cancello",
                        "description": "Comanda l'apertura fisica del cancello carraio per il Presidente Roberto Capobianco o personale autorizzato.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "motivo": {
                                    "type": "STRING",
                                    "description": "Motivo esatto dell'apertura del cancello."
                                }
                            },
                            "required": ["motivo"]
                        }
                    }]
                }]
            }
        }

    async def _receive_loop(self, ws):
        """Ascolta e processa i messaggi in arrivo da Google (Audio streaming e chiamate tool)."""
        while self._running:
            try:
                msg = await ws.recv()
                data = json.loads(msg)

                # Gestione Tool Calling (es. Apertura Cancello)
                if "toolCall" in data:
                    await self._handle_tool_call(ws, data["toolCall"])
                    continue

                server_content = data.get("serverContent", {})
                if not server_content:
                    continue

                # Gestione Interruzione / Barge-in (l'umano ha parlato sopra l'IA)
                if server_content.get("interrupted"):
                    logger.info(">>> [GEMINI LIVE] Interruzione vocale (barge-in): arresto audio immediato.")
                    get_audio_bus().stop()

                # Gestione Chunks Audio in arrivo
                model_turn = server_content.get("modelTurn", {})
                parts = model_turn.get("parts", [])
                for part in parts:
                    inline_data = part.get("inlineData", {})
                    if inline_data.get("mimeType", "").startswith("audio/pcm"):
                        raw_b64 = inline_data.get("data", "")
                        if raw_b64:
                            pcm_24k = base64.b64decode(raw_b64)
                            ulaw_8k = pcm24k_to_ulaw8k(pcm_24k)
                            if ulaw_8k:
                                get_audio_bus().play(
                                    ulaw_8k,
                                    priority=Priority.THOUGHT,
                                    label="GeminiLive:Voice",
                                    queue=True
                                )

            except Exception as e:
                logger.debug("Loop ricezione Live terminato: %s", e)
                break

    async def _handle_tool_call(self, ws, tool_call: dict):
        """Esegue il comando del cancello sul relè e risponde a Google confermando l'azione."""
        calls = tool_call.get("functionCalls", [])
        responses = []

        for call in calls:
            name = call.get("name")
            call_id = call.get("id")
            args = call.get("args", {})

            if name == "apri_cancello":
                motivo = args.get("motivo", "Autorizzato da Gemini Live")
                logger.info(">>> [GEMINI LIVE ACTION] Comando 'apri_cancello' ricevuto! Motivo: %s", motivo)

                # Esecuzione fisica tramite callback / relè
                success = True
                try:
                    if self.relay_callback:
                        self.relay_callback(motivo)
                    else:
                        from relay_controller import relay
                        relay.apri_cancello(channel=1, impulso_secondi=3.0)
                except Exception as ex:
                    logger.warning("Errore apertura relè da Gemini Live: %s", ex)
                    success = False

                responses.append({
                    "response": {
                        "output": {
                            "success": success,
                            "stato": "Relè cancello attivato con impulso 3.0s" if success else "Errore relè"
                        }
                    },
                    "id": call_id
                })

        # Invia la risposta del tool a Google per permettergli di formulare il saluto vocale
        if responses:
            tool_response_msg = {
                "toolResponse": {
                    "functionResponses": responses
                }
            }
            await ws.send(json.dumps(tool_response_msg))

    # ──────────────────────────────────────────────────────────────────────────
    # API PUBBLICA SINCRONA (THREAD-SAFE PER L'ORCHESTRATORE)
    # ──────────────────────────────────────────────────────────────────────────
    def feed_frame(self, image_bytes: bytes, camera: str = "corridoio"):
        """Invia un fotogramma video compresso (JPEG max 512px) a Gemini Live."""
        if not self._connected or not self._ws or not self._loop:
            return

        try:
            from orin_brain import optimize_image_for_vlm
            b64_jpeg = optimize_image_for_vlm(image_bytes, max_dim=512, quality=70)
        except Exception:
            b64_jpeg = base64.b64encode(image_bytes).decode("utf-8")

        msg = {
            "realtimeInput": {
                "mediaChunks": [{
                    "mimeType": "image/jpeg",
                    "data": b64_jpeg
                }]
            }
        }

        asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(msg)), self._loop)

    def feed_audio(self, pcm_16k_bytes: bytes):
        """Invia audio grezzo dal microfono Fanvil a Gemini Live."""
        if not self._connected or not self._ws or not self._loop:
            return

        b64_pcm = base64.b64encode(pcm_16k_bytes).decode("utf-8")
        msg = {
            "realtimeInput": {
                "mediaChunks": [{
                    "mimeType": "audio/pcm;rate=16000",
                    "data": b64_pcm
                }]
            }
        }
        asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(msg)), self._loop)

    def send_text(self, text: str):
        """Invia un messaggio di testo (es. comando manuale da dashboard)."""
        if not self._connected or not self._ws or not self._loop:
            return

        msg = {
            "clientContent": {
                "turns": [{
                    "role": "user",
                    "parts": [{"text": text}]
                }],
                "turnComplete": True
            }
        }
        asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(msg)), self._loop)


# Istanza singleton globale
gemini_live_engine = GeminiLiveEngine()
