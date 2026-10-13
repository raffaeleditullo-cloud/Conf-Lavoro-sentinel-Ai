#!/usr/bin/env python3
"""
ORIN CYBERNETIC INTELLIGENCE — MODULO CERVELLO CIBERNETICO (ORIN BRAIN)
Architettura di Visione Multimodale, Riconoscimento Relazionale e Dialogo Predittivo

Proprietà intellettuale: Conflavoro PMI — ORIN
Regolazione cognitiva: HEXAD Cybernetic Protocol (OCULUS, CORIS, ANIMA, MNEME, DEMON, PEIRA)
Modello Vision & Voice: Google Gemini 2.5 (Nativo Google Generative Language REST API)
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
import hashlib

logger = logging.getLogger("SentinelOrin")

try:
    from biometric_store import BiometricStore
except ImportError:
    from orchestrator.biometric_store import BiometricStore

# Integrazione Motore di Prosodia e Fonetica KERYX
try:
    from keryx_verbalizer import verbalize_for_speech
except ImportError:
    try:
        from orchestrator.keryx_verbalizer import verbalize_for_speech
    except ImportError:
        def verbalize_for_speech(t, max_chars=3500): return t

# Configurazione API Google Gemini (Cervello Visivo e Vocale Nativo)
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
DEFAULT_TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_ELEVEN_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
TIMEOUT_SECONDS = float(os.environ.get("ORIN_TIMEOUT_SECONDS", "8.0"))

# Banca dati biometrica dinamica (config/biometrics/, gestita dalla dashboard)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAX_GALLERY_FACES = 6   # limite di foto di riferimento inviate al modello per ogni analisi
DIALOGUE_LOG_MAX_BYTES = 512 * 1024
AUDIO_CACHE_DIR = os.path.join(os.path.dirname(__file__), "audio_cache")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)


def load_gemini_api_key() -> str:
    """Carica la chiave API Google Gemini da variabile d'ambiente o dal file protetto su disco."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    possible_paths = [
        os.path.expanduser("~/.secrets/Gemini Live API - ORIN/gemini live api.txt"),
        os.path.expanduser("~/.secrets/gemini_api_key.txt"),
        os.path.expanduser("~/.secrets/gemini live api.txt"),
        "/root/.secrets/gemini live api.txt",
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    k = f.read().strip()
                    if k:
                        return k
            except Exception:
                pass
    return ""


def load_elevenlabs_api_key() -> str:
    """Carica la chiave API ElevenLabs da variabile d'ambiente o dai file protetti su disco."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    possible_paths = [
        os.path.expanduser("~/.secrets/ElevenLabs Api.txt"),
        os.path.expanduser("~/.secrets/elevenlabs_api_key.txt"),
        os.path.expanduser("~/.secrets/elevenlabs.txt"),
        "/root/.secrets/ElevenLabs Api.txt",
        "c:/Users/stree/Desktop/HEXAD B-1/.env",
        os.path.expanduser("~/Desktop/HEXAD B-1/.env"),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "ELEVENLABS_API_KEY=" in content:
                        for line in content.splitlines():
                            if line.strip().startswith("ELEVENLABS_API_KEY="):
                                k = line.split("=", 1)[1].strip()
                                if k:
                                    return k
                    else:
                        k = content.strip()
                        if k and not k.startswith("#"):
                            return k
            except Exception:
                pass
    return ""


def optimize_image_for_vlm(image_bytes: bytes, max_dim: int = 384, quality: int = 65) -> str:
    """Comprime l'immagine in RAM a 384px JPEG per abbattere i tempi di upload di rete a meno di 15ms."""
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
    Cervello visivo e interattivo di ORIN basato su Google Gemini e ElevenLabs Turbo.
    Analizza i fotogrammi dei varchi, comprende le azioni, riconosce le identità autorizzate
    e genera frasi e audio con intelligenza neurale a latenza ultra-bassa (<2s).
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or load_gemini_api_key()
        self.elevenlabs_api_key = load_elevenlabs_api_key()
        raw_model = (model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL).replace("models/", "")
        # Normalizzazione automatica: se è rimasto configurato un vecchio modello 2.x o 1.x dismesso da Google (404), usa gemini-flash-lite-latest
        if any(raw_model.startswith(p) for p in ("gemini-2.", "gemini-1.", "gemini-2-", "gemini-1-")):
            raw_model = "gemini-flash-lite-latest"
        self.model = raw_model
        self.biometrics = BiometricStore(os.environ.get("CONFIG_DIR") or os.path.join(BASE_DIR, "config"))
        self._gallery = []          # [{"profile": {...}, "face_b64": "..."}]
        self._gallery_mtime = -1.0
        self._load_biometric_profiles()

    def is_active(self) -> bool:
        """Verifica se l'API Google Gemini è configurata e pronta."""
        return bool(self.api_key or load_gemini_api_key())

    def _load_biometric_profiles(self, force: bool = False) -> list:
        """
        Carica la galleria dei volti autorizzati da config/biometrics/.
        Si ricarica da sola quando la dashboard registra o revoca un profilo
        (controllo sul mtime di profiles.json): nessun riavvio dell'orchestratore.
        """
        mtime = self.biometrics.mtime()
        if not force and mtime == self._gallery_mtime:
            return self._gallery
        gallery = []
        for profile in self.biometrics.list_profiles():
            face_path = self.biometrics.media_path("face", profile["id"])
            if not face_path:
                continue
            try:
                with open(face_path, "rb") as f:
                    face_b64 = optimize_image_for_vlm(f.read(), max_dim=320, quality=70)
                gallery.append({"profile": profile, "face_b64": face_b64})
            except Exception as e:
                logger.warning("Profilo biometrico %s: foto non caricabile (%s)", profile.get("id"), e)
        self._gallery = gallery
        self._gallery_mtime = mtime
        logger.info(">>> [ORIN] Galleria biometrica: %d profili autorizzati (%s)",
                    len(gallery), ", ".join(g["profile"].get("name", "?") for g in gallery) or "nessuno")
        return gallery

    def _log_dialogue(self, entry: Dict[str, Any]):
        """Accoda una battuta del dialogo interfonico per il feed live della dashboard."""
        log_dir = os.environ.get("LOG_DIR") or ("/app/logs" if os.path.isdir("/app/logs") else os.path.join(BASE_DIR, "storage", "logs"))
        path = os.path.join(log_dir, "orin_dialogue.jsonl")
        try:
            os.makedirs(log_dir, exist_ok=True)
            if os.path.exists(path) and os.path.getsize(path) > DIALOGUE_LOG_MAX_BYTES:
                with open(path, "r", encoding="utf-8") as f:
                    tail = f.readlines()[-100:]
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(tail)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("Dialogo non registrato nel feed: %s", e)

    @staticmethod
    def _apply_identity(result: Dict[str, Any], gallery: list):
        """
        Valida il riconoscimento del modello contro la galleria reale e applica le regole del profilo.
        Un ID inventato o non presente in galleria viene scartato; apertura cancello e saluto
        derivano dal profilo registrato, non dal testo generato dal modello.
        """
        matched_id = result.pop("matched_profile_id", None)
        entry = next((g for g in gallery if g["profile"]["id"] == matched_id), None) if matched_id else None
        if not entry or not result.get("is_person_present", True):
            result.update({"subject_identified": False, "identity_id": None, "identity_name": None,
                           "is_president": False, "open_gate": False})
            return
        prof = entry["profile"]
        result.update({
            "subject_identified": True,
            "identity_id": prof["id"],
            "identity_name": prof.get("name"),
            "identity_role": prof.get("role"),
            "open_gate": bool(prof.get("open_gate")),
            "threat_level": "none",
            "spoken_message": prof.get("greeting") or f"Benvenuto {prof.get('name', '')}.",
        })
        # Alias storico: demon_gate e identikit_profiler leggono ancora 'is_president'
        result["is_president"] = True

    def _build_system_prompt(self, is_armed: bool, camera: str, gallery: Optional[list] = None) -> str:
        """Costruisce il prompt HEXAD disciplinato e differenziato per stato di armamento."""
        if is_armed:
            status_section = (
                "STATO OPERATIVO: SISTEMA ARMATO (MODALITÀ NOTTE / ASSENTE).\n"
                "• L'accesso a quest'area ('{camera}') NON È CONSENTITO a quest'ora (eccetto le identità autorizzate della galleria).\n"
                "• TONO DELLA VOCE: PERENTORIO, SEVERO, FERMO E DISSUASIVO.\n"
                "• NON USARE MAI frasi preconfezionate, saluti di cortesia o 'benvenuto'.\n"
                "• RAGIONAMENTO VISIVO: Osserva con precisione cosa sta facendo la persona (postura, movimento, posizione, oggetti) e intimale direttamente a voce di fermarsi e andarsene (es. 'Alt! Ti vedo vicino alla porta. Allontanati immediatamente dall\\'area!').\n"
                "• Imposta 'threat_level': 'high' (o 'medium').\n"
            ).format(camera=camera)
        else:
            status_section = (
                "STATO OPERATIVO: MONITORAGGIO SILENZIOSO (MODALITÀ CASA / DIURNO).\n"
                "• Presidio aziendale attivo o transito ordinario di dipendenti e corrieri.\n"
                "• TONO DELLA VOCE: Cordiale, educato e discreto se è un lavoratore o visitatore (es. 'Buongiorno, benvenuto in Conf-Lavoro.').\n"
                "• Imposta 'threat_level': 'low' o 'none'.\n"
            )

        return (
            "Tu sei ORIN, la sentinella e custode cibernetico intelligente di Conflavoro PMI.\n"
            "Possiedi gli occhi delle telecamere e ragioni in tempo reale su ogni fotogramma per proteggere la sede aziendale.\n"
            "Non usi frasi preconfezionate o stereotipate: osservi la scena e formuli spontaneamente il pensiero vocale più calzante.\n\n"
            f"{status_section}\n"
            "LINEE GUIDA RIGOROSE (HEXAD PROTOCOL):\n"
            "1. ONESTÀ PERCETTIVA & PRESENZA UMANA REALE: Verifica prima di tutto se nell'inquadratura è fisicamente presente un essere umano reale in carne ed ossa (visibile testa, busto o gambe). "
            "I sensori di movimento possono attivarsi per cambi di luce, ombre o oggetti inanimati (biciclette parcheggiate, sedie, scatoloni, piante). "
            "Se NON vedi con certezza una persona viva, imposta 'is_person_present': false, 'threat_level': 'none', 'spoken_message': '' e non inventare persone o azioni inesistenti.\n"
            "2. CONFRONTO VOLTO: Ti viene fornita una galleria di foto di riferimento di persone AUTORIZZATE, ciascuna con il proprio ID. "
            "Se la persona inquadrata corrisponde con certezza ai tratti somatici di UNA di esse, restituisci il suo ID in 'matched_profile_id'. "
            "Nel dubbio, o se non sono presenti riferimenti, restituisci null: un falso riconoscimento è molto peggio di un mancato riconoscimento.\n"
            "3. ACCOGLIENZA: per le persone riconosciute saluto e apertura varco sono decisi dal sistema in base al profilo; tu compila solo i campi.\n"
            "4. RICONOSCIMENTO AZIONI: Se è presente una persona reale, osserva cosa fa con precisione oggettiva.\n"
            "5. CARATTERE E BREVITÀ: La frase parlata ('spoken_message') deve essere di MASSIMO 10-14 parole, secca, incisiva e naturale per la voce neurale italiana. Deve riflettere l'azione reale osservata nell'inquadratura. Se is_person_present è false, spoken_message deve essere una stringa vuota \"\".\n\n"
            "Rispondi ESCLUSIVAMENTE in formato JSON valido con questa struttura:\n"
            "{\n"
            '  "is_person_present": boolean,\n'
            '  "matched_profile_id": "ID del riferimento autorizzato riconosciuto, oppure null",\n'
            '  "subject_description": "descrizione sintetica abbigliamento e tratti certi (oppure \'Nessuna persona presente\')",\n'
            '  "action_detected": "cosa sta facendo esattamente (oppure \'Nessuna azione - oggetto inanimato o vuoto\')",\n'
            '  "threat_level": "none" | "low" | "medium" | "high",\n'
            '  "spoken_message": "la frase esatta in italiano che ORIN deve pronunciare a voce (stringa vuota se nessuna persona)",\n'
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
        Analizza un fotogramma JPEG della telecamera via Google Gemini 2.5 Flash nativo.
        Restituisce il verdetto analitico e il messaggio vocale generato da ORIN.
        """
        t0 = time.time()
        api_key = self.api_key or load_gemini_api_key()
        gallery = self._load_biometric_profiles()[:MAX_GALLERY_FACES]

        if not api_key:
            logger.debug("ORIN: GEMINI_API_KEY non configurata, fallback nominale.")
            return self._fallback_response(is_armed, "Chiave API Gemini assente")

        try:
            target_b64 = optimize_image_for_vlm(image_bytes, max_dim=512, quality=75)

            # Costruzione dei contenuti per il modello multimodale Google Gemini
            parts = []
            
            # Galleria dei volti autorizzati: una foto di riferimento per ogni profilo
            for entry in gallery:
                prof = entry["profile"]
                parts.append({"text": f"RIFERIMENTO AUTORIZZATO (ID: {prof['id']}): {prof.get('name', '')}."})
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": entry["face_b64"]}})

            state_label = "ARMATO (NOTTE / ASSENTE)" if is_armed else "DISARMATO (CASA / DIURNO)"
            parts.append({
                "text": f"IMMAGINE TARGET: Telecamera '{camera}' [Stato Impianto: {state_label}]. Analizza il soggetto inquadrato ora:"
            })
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": target_b64
                }
            })

            payload = {
                "system_instruction": {
                    "parts": [{"text": self._build_system_prompt(is_armed, camera, gallery)}]
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": parts
                    }
                ],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                    "max_output_tokens": 800
                }
            }

            url = f"{GEMINI_API_BASE}/{self.model}:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json"
                }
            )

            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                latency_ms = round((time.time() - t0) * 1000, 1)

                candidates = res_data.get("candidates", [])
                if not candidates:
                    logger.warning("ORIN: Nessun candidato restituito da Gemini.")
                    return self._fallback_response(is_armed, "Risposta vuota da Gemini")

                content_parts = candidates[0].get("content", {}).get("parts", [])
                raw_content = ""
                for p in content_parts:
                    if "text" in p:
                        raw_content += p["text"]

                result = json.loads(raw_content)
                result["latency_ms"] = latency_ms
                result["engine"] = f"google/{self.model}"
                self._apply_identity(result, gallery)

                logger.info(
                    ">>> [ORIN BRAIN - GOOGLE GEMINI] Elaborazione completata in %.0fms: Identità=%s | Minaccia=%s | Msg: '%s'",
                    latency_ms, result.get("identity_name") or "-", result.get("threat_level"), result.get("spoken_message")
                )
                return result

        except urllib.error.HTTPError as http_err:
            logger.warning("ORIN Gemini API HTTP Error (%d): %s", http_err.code, http_err.reason)
            return self._fallback_response(is_armed, f"HTTP Error {http_err.code}")
        except Exception as e:
            logger.warning("ORIN Gemini Vision Timeout / Errore (%.0fms): %s", (time.time() - t0) * 1000, e)
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
            "is_person_present": is_armed,
            "is_president": False,
            "subject_identified": False,
            "identity_name": None,
            "subject_description": "Soggetto rilevato da sensore ottico" if is_armed else "Nessuna persona certa",
            "action_detected": "Transito varco" if is_armed else "Nessuna azione",
            "threat_level": threat,
            "spoken_message": msg if is_armed else "",
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
    ) -> bool:
        """
        Sintetizza il testo con Google Gemini (voce Charon o Kore) direttamente in
        G.711 mu-law 8 kHz e lo consegna all'AudioBus,
        che lo diffonde sul Fanvil A233 senza processi ffmpeg ne' file temporanei.

        La frase ha priorita' THOUGHT ed e' accodata: se un annuncio precedente
        e' ancora in onda, ORIN parla subito dopo, senza pause.
        Restituisce True se l'annuncio e' stato accettato dall'AudioBus.
        """
        if not text or not text.strip():
            return False

        # 1. Normalizzazione fonetica, accenti e prosodia KERYX
        spoken_text = verbalize_for_speech(text)
        if not spoken_text or not spoken_text.strip():
            spoken_text = text

        # 2. Cache locale permanente SHA256 (0 ms di latenza per frasi frequenti)
        audio_ulaw = self._read_voice_cache(voice_pack, spoken_text)

        # 3. Sintesi ElevenLabs (voce ufficiale) se la frase non e' in cache.
        #    Solo l'audio ElevenLabs va in cache: il ripiego Gemini TTS viene riprodotto
        #    ma non memorizzato, per non sostituire per sempre la voce ufficiale.
        if not audio_ulaw:
            audio_ulaw = self._synthesize_elevenlabs(spoken_text, voice_pack)
            if audio_ulaw:
                self._write_voice_cache(voice_pack, spoken_text, audio_ulaw)
            else:
                audio_ulaw = self._synthesize_gemini_tts(spoken_text, voice_pack, volume_percent)
                if not audio_ulaw:
                    return False

        # 4. Diffusione tramite AudioBus (unico proprietario dell'altoparlante)
        from rtp_audio_bus import Priority, get_audio_bus
        return get_audio_bus().play(
            audio_ulaw,
            priority=Priority.THOUGHT,
            label=f"ORIN:{voice_pack}",
            volume_percent=volume_percent,
            queue=True,
        )

    def hear_and_respond(
        self,
        audio_bytes: bytes,
        context_image_bytes: Optional[bytes] = None,
        camera: Optional[str] = None,
        voice_pack: str = "carmelo",
        volume_percent: float = 70.0,
        play_response: bool = True,
    ) -> Dict[str, Any]:
        """
        Interazione conversazionale bidirezionale (Passo C):
        Ascolta la voce catturata dal microfono, comprende il significato e l'intento,
        osserva il fotogramma della telecamera (se disponibile) e risponde a voce
        sull'altoparlante Fanvil A233 con la voce ufficiale di Carmelo La Rosa.
        """
        if not self.is_active():
            return {"error": "Gemini API key non configurata", "reply": "", "transcription": ""}

        t0 = time.time()
        try:
            parts = []
            authorized = [g["profile"] for g in self._load_biometric_profiles()]
            authorized_names = ", ".join(p.get("name", "") for p in authorized if p.get("name"))

            # 1. Prompt di ruolo e comportamento istituzionale
            system_instruction = (
                "Sei ORIN, il sistema di sicurezza, accoglienza e vigilanza vocale autonoma per la sede Conflavoro PMI.\n"
                "Parli con la voce ufficiale maschile di Carmelo.\n"
                "Un operatore, visitatore o custode ha appena parlato al microfono.\n"
                "ISTRUZIONI:\n"
                "1. Ascolta attentamente ciò che ha detto l'interlocutore.\n"
                "2. Se l'audio contiene solo fruscio, colpi di tosse, click o nessuna parola comprensibile, imposta 'reply' su '' e 'intent' su 'silence'.\n"
                "3. Se l'interlocutore esegue un test audio (es. 'prova', 'test radio', 'mi senti?'), conferma con precisione professionale che la trasmissione e la modulazione sono ricevute forte e chiaro.\n"
                "4. Se l'interlocutore chiede informazioni, orari o indicazioni, rispondi con cortesia istituzionale, precisione e brevità.\n"
                "5. Se l'interlocutore saluta o si presenta, rispondi cordialmente.\n"
                "6. Se il soggetto nell'immagine mostra atteggiamento sospetto o tenta manomissioni, mantieni tono fermo e autoritario di allarme.\n"
                "7. ACCESSO VOCALE: Persone autorizzate registrate: [" + (authorized_names or "nessuna") + "]. "
                "Se l'interlocutore si presenta pronunciando chiaramente il nome di UNA di esse (es. 'Sono <nome>, autorizzazione per ORIN'), "
                "imposta 'claimed_identity' con il nome ESATTO come scritto nell'elenco; altrimenti null. Non indovinare: solo nome realmente pronunciato.\n"
                "8. LUNGHEZZA MASSIMA DELLA RISPOSTA: 1 o massimo 2 frasi brevi, sintetiche e incisive (ottimizzate per altoparlante IP industriale).\n"
                "Rispondi ESCLUSIVAMENTE in formato JSON puro con questi campi:\n"
                "{\n"
                '  "transcription": "<trascrizione fedele in italiano delle parole dette>",\n'
                '  "reply": "<la tua risposta parlata in italiano>",\n'
                '  "intent": "<test | greeting | info | threat | silence | unknown>",\n'
                '  "claimed_identity": "<nome autorizzato pronunciato oppure null>"\n'
                "}"
            )
            parts.append({"text": system_instruction})

            # 2. Immagine di contesto visivo (se presente)
            if context_image_bytes:
                img_b64 = optimize_image_for_vlm(context_image_bytes, max_dim=384, quality=65)
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_b64
                    }
                })

            # 3. Audio dell'utente
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": "audio/wav",
                    "data": audio_b64
                }
            })

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.15,
                    "maxOutputTokens": 200,
                    "responseMimeType": "application/json"
                }
            }

            url = f"{GEMINI_API_BASE}/{self.model}:generateContent?key={self.api_key}"
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency_ms = (time.time() - t0) * 1000

                candidates = data.get("candidates", [])
                if not candidates:
                    return {"transcription": "", "reply": "", "intent": "unknown", "latency_ms": latency_ms}

                content_parts = candidates[0].get("content", {}).get("parts", [])
                raw_text = "".join(p.get("text", "") for p in content_parts).strip()
                result = json.loads(raw_text)
                result["latency_ms"] = latency_ms

                transcription = result.get("transcription", "").strip()
                reply = result.get("reply", "").strip()
                intent = result.get("intent", "").strip().lower()

                logger.info(
                    ">>> [ORIN BRAIN - AUDIO DIALOGUE] Udito: '%s' | Risposta: '%s' | Intent: %s (%.0fms)",
                    transcription, reply, intent, latency_ms
                )

                # Validazione accesso vocale: il nome dichiarato deve esistere davvero in archivio.
                # E' un controllo di frase/nome, non una verifica biometrica dell'impronta vocale:
                # per questo NON aziona il relè, conferma solo l'identita' dichiarata.
                claimed = str(result.get("claimed_identity") or "").strip().lower()
                matched = next((p for p in authorized if claimed and p.get("name", "").strip().lower() == claimed), None)
                result["voice_access_validated"] = bool(matched)
                result["identity_name"] = matched.get("name") if matched else None
                if matched and intent != "silence":
                    reply = matched.get("greeting") or reply
                    result["reply"] = reply

                self._log_dialogue({
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "camera": camera,
                    "transcription": transcription,
                    "reply": reply if intent != "silence" else "",
                    "intent": intent,
                    "identity_name": result["identity_name"],
                    "latency_ms": round(latency_ms),
                })

                if play_response and reply and intent != "silence":
                    self.speak(reply, voice_pack=voice_pack, volume_percent=volume_percent)

                return result

        except Exception as e:
            logger.warning("ORIN hear_and_respond Errore: %s", e)
            return {"error": str(e), "reply": "", "transcription": "", "intent": "error", "latency_ms": (time.time() - t0) * 1000}


    @staticmethod
    def _voice_cache_key(voice_pack: str, spoken_text: str) -> str:
        # La chiave include l'ID voce ElevenLabs effettivo: cambiando voce (o dopo le prove
        # del 12/10 con Adam e Gemini TTS) le vecchie frasi in cache non vengono riutilizzate.
        pack = (voice_pack or "carmelo").strip().lower()
        if pack in ("sami", "kore"):
            vid = os.environ.get("ELEVENLABS_VOICE_SAMI", "Ap2b3ZnSIW7h0QbBbxCq")
        elif len(pack) >= 20 and " " not in pack:
            vid = voice_pack.strip()
        else:
            vid = os.environ.get("ELEVENLABS_VOICE_CARMELO", "HuK8QKF35exsCh2e7fLT")
        return hashlib.sha256(f"el:{vid}::{spoken_text}".encode("utf-8")).hexdigest()[:20]

    def _read_voice_cache(self, voice_pack: str, spoken_text: str) -> Optional[bytes]:
        """Legge la frase dalla cache mu-law; converte una sola volta le vecchie voci MP3."""
        from ulaw_audio import ensure_ulaw
        key = self._voice_cache_key(voice_pack, spoken_text)
        ulaw_file = os.path.join(AUDIO_CACHE_DIR, f"{key}.ulaw")
        legacy_mp3 = os.path.join(AUDIO_CACHE_DIR, f"{key}.mp3")
        try:
            if os.path.exists(ulaw_file) and os.path.getsize(ulaw_file) > 100:
                with open(ulaw_file, "rb") as cf:
                    audio = cf.read()
                logger.info(">>> [ORIN VOICE CACHE] Frase pronta da cache locale in RAM (0 ms): '%s'", key)
                return audio
            if os.path.exists(legacy_mp3) and os.path.getsize(legacy_mp3) > 100:
                with open(legacy_mp3, "rb") as cf:
                    audio = ensure_ulaw(cf.read(), declared="mp3", source=legacy_mp3)
                if audio:
                    self._write_voice_cache(voice_pack, spoken_text, audio)
                    logger.info(">>> [ORIN VOICE CACHE] Voce MP3 storica convertita in mu-law: '%s'", key)
                return audio
        except Exception as e:
            logger.debug("Impossibile leggere la cache vocale: %s", e)
        return None

    def _write_voice_cache(self, voice_pack: str, spoken_text: str, audio_ulaw: bytes):
        key = self._voice_cache_key(voice_pack, spoken_text)
        try:
            with open(os.path.join(AUDIO_CACHE_DIR, f"{key}.ulaw"), "wb") as cf:
                cf.write(audio_ulaw)
            logger.info(">>> [ORIN VOICE CACHE] Salvata nuova frase in cache locale: '%s'", key)
        except Exception as ce:
            logger.debug("Impossibile salvare cache audio: %s", ce)

    @classmethod
    def _synthesize_ulaw(cls, spoken_text: str, voice_pack: str, volume_percent: float) -> Optional[bytes]:
        """
        Sintesi vocale ad altissima velocita':
        1. ElevenLabs Turbo v2.5 nativo in G.711 mu-law 8 kHz (~350-500ms, zero transcoding).
        2. Fallback fail-safe su Google Gemini TTS se ElevenLabs non e' configurato o in caso di errore.
        """
        # 1. Tentativo prioritario con ElevenLabs Turbo v2.5
        audio_ulaw = cls._synthesize_elevenlabs(spoken_text, voice_pack)
        if audio_ulaw:
            return audio_ulaw

        # 2. Fallback automatico su Google Gemini TTS
        return cls._synthesize_gemini_tts(spoken_text, voice_pack, volume_percent)

    @staticmethod
    def _synthesize_elevenlabs(spoken_text: str, voice_pack: str) -> Optional[bytes]:
        """
        Sintesi ElevenLabs Turbo v2.5 in mu-law 8 kHz grezzo (formato nativo del Fanvil A233).
        Configurazione collaudata in campo (commit 65949f2): voci italiane native,
        stabilita' 0.70, endpoint /stream con optimize_streaming_latency=3.
        """
        from ulaw_audio import ensure_ulaw

        api_key = load_elevenlabs_api_key()
        if not api_key:
            return None

        # Voci italiane native collaudate (NON usare voci inglesi: storpiano l'italiano)
        carmelo_id = os.environ.get("ELEVENLABS_VOICE_CARMELO", "HuK8QKF35exsCh2e7fLT")  # Carmelo La Rosa
        sami_id = os.environ.get("ELEVENLABS_VOICE_SAMI", "Ap2b3ZnSIW7h0QbBbxCq")        # Alessandra
        voices = {
            "carmelo": carmelo_id,
            "sami": sami_id,
            "charon": carmelo_id,
            "kore": sami_id,
        }

        # Supporto ad ID ElevenLabs passati direttamente (lunghezza >= 20)
        cleaned_voice = voice_pack.strip()
        if len(cleaned_voice) >= 20 and " " not in cleaned_voice:
            voice_id = cleaned_voice
        else:
            voice_id = voices.get(cleaned_voice.lower(), voices["carmelo"])

        model_id = os.environ.get("ELEVENLABS_MODEL", DEFAULT_ELEVEN_MODEL)
        url = f"{ELEVENLABS_API_BASE}/{voice_id}/stream?output_format=ulaw_8000&optimize_streaming_latency=3"

        payload = {
            "text": spoken_text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.70,
                "similarity_boost": 0.85
            }
        }

        try:
            t0 = time.time()
            logger.info(">>> [ORIN VOICE - ELEVENLABS TURBO] Avvio sintesi (%s -> %s) -> '%s'", voice_pack, voice_id, spoken_text)
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                }
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read()
            audio_ulaw = ensure_ulaw(raw, declared="ulaw", source="ElevenLabs")
            if not audio_ulaw or len(audio_ulaw) <= 100:
                logger.warning(">>> [ORIN VOICE] Nessun dato audio valido da ElevenLabs, passaggio a Gemini TTS...")
                return None
            logger.info(
                ">>> [ORIN VOICE - ELEVENLABS TURBO] Sintesi completata in %.0f ms (%.1f s audio mu-law)",
                (time.time() - t0) * 1000.0, len(audio_ulaw) / 8000.0
            )
            return audio_ulaw
        except Exception as e:
            logger.warning(">>> [ORIN VOICE] ElevenLabs Turbo non disponibile (%s), passaggio a Gemini TTS...", e)
            return None

    @staticmethod
    def _synthesize_gemini_tts(spoken_text: str, voice_pack: str, volume_percent: float) -> Optional[bytes]:
        """Sintesi vocale fail-safe Google Gemini con voce neurale nativa convertita in mu-law 8 kHz."""
        from ulaw_audio import pcm24k_to_ulaw8k

        api_key = load_gemini_api_key()
        if not api_key:
            logger.info(">>> [ORIN VOICE] GEMINI_API_KEY non trovata: riproduzione traccia offline di fallback.")
            return None

        voices = {
            "carmelo": "Charon",
            "sami": "Kore",
            "charon": "Charon",
            "kore": "Kore",
            "puck": "Puck",
            "fenrir": "Fenrir",
            "aoede": "Aoede"
        }
        voice_name = voices.get(voice_pack.lower(), "Charon")
        tts_model = os.environ.get("GEMINI_TTS_MODEL", DEFAULT_TTS_MODEL).replace("models/", "")
        url = f"{GEMINI_API_BASE}/{tts_model}:generateContent?key={api_key}"

        try:
            t0 = time.time()
            logger.info(">>> [ORIN VOICE - GOOGLE TTS] Avvio sintesi neurale (%s -> %s) -> '%s' (vol: %.0f%%)", voice_pack, voice_name, spoken_text, volume_percent)

            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": f"Leggi con voce naturale e tono appropriato in lingua italiana: {spoken_text}"}
                        ]
                    }
                ],
                "generationConfig": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": voice_name
                            }
                        }
                    }
                }
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json"
                }
            )

            with urllib.request.urlopen(req, timeout=6.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))

            candidates = res_data.get("candidates", [])
            if not candidates:
                logger.warning(">>> [ORIN VOICE] Nessun audio restituito da Google Gemini.")
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            raw_pcm = None
            for p in parts:
                inline = p.get("inlineData", {})
                if inline and inline.get("data"):
                    raw_pcm = base64.b64decode(inline["data"])
                    break

            if not raw_pcm:
                logger.warning(">>> [ORIN VOICE] Dati audio assenti nella risposta Google Gemini.")
                return None

            # Converte il flusso 24kHz 16-bit PCM in mu-law 8kHz nativo Fanvil A233
            audio_ulaw = pcm24k_to_ulaw8k(raw_pcm)
            logger.info(
                ">>> [ORIN VOICE - GOOGLE TTS] Sintesi neurale completata in %.0f ms (%.1f s audio mu-law)",
                (time.time() - t0) * 1000.0, len(audio_ulaw) / 8000.0
            )
            return audio_ulaw
        except Exception as e:
            logger.warning(">>> [ORIN VOICE] Errore sintesi Google Gemini: %s (uso fallback locale)", e)
            return None


# Istanza singleton globale
orin_brain = OrinBrain()

