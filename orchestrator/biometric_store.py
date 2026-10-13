#!/usr/bin/env python3
"""
ORIN — Banca dati biometrica multi-profilo (viso + voce).

Unica fonte di verita' condivisa da dashboard (enrollment/revoca) e da OrinBrain
(galleria dei volti autorizzati). Tutto vive in <config>/biometrics/:

    profiles.json        indice dei profili (metadati, nessun dato binario)
    faces/<id>.jpg       fototessera di riferimento
    voices/<id>.wav      impronta vocale registrata (PCM WAV)

Nessun dato di esempio: l'archivio parte vuoto e si popola solo con registrazioni reali.
"""

import base64
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

MAX_FACE_BYTES = 2 * 1024 * 1024
MAX_VOICE_BYTES = 4 * 1024 * 1024
MAX_PROFILES = 24

_ID_RE = re.compile(r"^[a-f0-9]{12}$")
_lock = threading.Lock()


class BiometricError(ValueError):
    """Errore di validazione con messaggio leggibile dall'operatore."""


def default_config_dir() -> str:
    env = os.environ.get("CONFIG_DIR")
    if env:
        return env
    if os.path.isdir("/config"):
        return "/config"
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config"))


class BiometricStore:
    def __init__(self, config_dir: Optional[str] = None):
        self.root = os.path.join(config_dir or default_config_dir(), "biometrics")
        self.faces_dir = os.path.join(self.root, "faces")
        self.voices_dir = os.path.join(self.root, "voices")
        self.index_path = os.path.join(self.root, "profiles.json")

    # ── lettura ────────────────────────────────────────────────────────────
    def mtime(self) -> float:
        try:
            return os.path.getmtime(self.index_path)
        except OSError:
            return 0.0

    def list_profiles(self) -> List[Dict[str, Any]]:
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        profiles = data.get("profiles", []) if isinstance(data, dict) else []
        return [p for p in profiles if isinstance(p, dict) and _ID_RE.match(str(p.get("id", "")))]

    def get(self, profile_id: str) -> Optional[Dict[str, Any]]:
        return next((p for p in self.list_profiles() if p["id"] == profile_id), None)

    def media_path(self, kind: str, profile_id: str) -> Optional[str]:
        """Percorso del file media, solo per ID ben formati (nessun path traversal)."""
        if not _ID_RE.match(profile_id or ""):
            return None
        folder, ext = (self.faces_dir, "jpg") if kind == "face" else (self.voices_dir, "wav")
        path = os.path.join(folder, f"{profile_id}.{ext}")
        return path if os.path.isfile(path) else None

    def public_view(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        pid = profile["id"]
        return {
            "id": pid,
            "name": profile.get("name", ""),
            "role": profile.get("role", ""),
            "open_gate": bool(profile.get("open_gate")),
            "greeting": profile.get("greeting", ""),
            "enrolled_at": profile.get("enrolled_at", ""),
            "has_face": self.media_path("face", pid) is not None,
            "has_voice": self.media_path("voice", pid) is not None,
        }

    # ── scrittura ──────────────────────────────────────────────────────────
    @staticmethod
    def _decode(b64: str, label: str, limit: int) -> bytes:
        if not isinstance(b64, str) or not b64:
            raise BiometricError(f"{label} mancante")
        if "," in b64[:80] and b64.lstrip().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        try:
            raw = base64.b64decode(b64, validate=False)
        except Exception:
            raise BiometricError(f"{label} non decodificabile")
        if not raw or len(raw) > limit:
            raise BiometricError(f"{label} vuoto o troppo grande")
        return raw

    @staticmethod
    def _atomic_write(path: str, data: bytes):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _write_index(self, profiles: List[Dict[str, Any]]):
        payload = json.dumps({"version": 1, "profiles": profiles}, indent=2, ensure_ascii=False)
        self._atomic_write(self.index_path, payload.encode("utf-8"))

    def enroll(self, name: str, role: str, open_gate: bool, greeting: str,
               face_b64: str, audio_b64: Optional[str] = None) -> Dict[str, Any]:
        name = " ".join(str(name or "").split())[:80]
        role = " ".join(str(role or "").split())[:120]
        greeting = " ".join(str(greeting or "").split())[:200]
        if len(name) < 3:
            raise BiometricError("Nome e cognome obbligatori")

        face = self._decode(face_b64, "Foto del volto", MAX_FACE_BYTES)
        if not face.startswith(b"\xff\xd8\xff"):
            raise BiometricError("La foto del volto deve essere un JPEG valido")

        voice = None
        if audio_b64:
            voice = self._decode(audio_b64, "Registrazione vocale", MAX_VOICE_BYTES)
            if not (voice[:4] == b"RIFF" and voice[8:12] == b"WAVE"):
                raise BiometricError("La registrazione vocale deve essere un file WAV valido")

        with _lock:
            profiles = self.list_profiles()
            if len(profiles) >= MAX_PROFILES:
                raise BiometricError(f"Limite di {MAX_PROFILES} profili raggiunto")
            pid = uuid.uuid4().hex[:12]
            self._atomic_write(os.path.join(self.faces_dir, f"{pid}.jpg"), face)
            if voice:
                self._atomic_write(os.path.join(self.voices_dir, f"{pid}.wav"), voice)
            profile = {
                "id": pid,
                "name": name,
                "role": role,
                "open_gate": bool(open_gate),
                "greeting": greeting,
                "enrolled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            profiles.append(profile)
            self._write_index(profiles)
        return profile

    def delete(self, profile_id: str) -> bool:
        if not _ID_RE.match(profile_id or ""):
            return False
        with _lock:
            profiles = self.list_profiles()
            remaining = [p for p in profiles if p["id"] != profile_id]
            if len(remaining) == len(profiles):
                return False
            self._write_index(remaining)
            for kind in ("face", "voice"):
                path = self.media_path(kind, profile_id)
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
        return True
