#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — AudioBus: unico proprietario dell'altoparlante Fanvil A233

PERCHE' ESISTE
In precedenza ogni annuncio avviava un processo ffmpeg separato e il driver
speaker, ORIN e i ripieghi non si coordinavano: due flussi potevano sovrapporsi
sullo stesso canale multicast e ogni avvio di ffmpeg costava centinaia di ms.
L'AudioBus e' un solo thread che trasmette l'audio in RTP direttamente da Python.
Tutti i moduli gli consegnano audio mu-law gia' pronto con una priorita'.

PROTOCOLLO (identico a quello collaudato con ffmpeg)
- RTP su UDP multicast verso FANVIL_MULTICAST_IP:FANVIL_MULTICAST_PORT.
- Payload type 0 (G.711 mu-law), 8 kHz mono, 20 ms per pacchetto (160 byte).
- Marker bit sul primo pacchetto di ogni sequenza parlata (talkspurt).
- Cadenza scandita dal clock monotono assoluto: nessun accumulo di ritardo.

REGOLE DI PRIORITA'
- Una richiesta con priorita' PIU' ALTA di quella in onda la interrompe subito
  (il canale resta aperto: nessun nuovo pre-roll).
- A priorita' uguale o inferiore: accodata se `queue=True` (riproduzione
  contigua, es. il Riflesso seguito dal pensiero di ORIN), altrimenti scartata.

PARAMETRI (variabili d'ambiente)
- FANVIL_RTP_DELAY_MS: silenzio iniziale che dà tempo all'amplificatore del
  Fanvil di aprirsi (sostituisce il vecchio filtro 'adelay'). Default 300.
- FANVIL_RTP_HOLD_MS: silenzio trasmesso dopo l'ultimo annuncio per tenere aperto
  il canale; se nel frattempo arriva altro audio non serve un nuovo pre-roll.
  Default 0 (comportamento storico). Da collaudare in campo, es. 4000.
- FANVIL_MULTICAST_IFACE_IP: IP locale dell'interfaccia LAN da usare per il
  multicast (consigliato con network_mode: host, dove esiste anche docker0).
- FANVIL_MULTICAST_TTL: TTL multicast. Default 16 (come ffmpeg).
"""

import os
import random
import socket
import struct
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

from ulaw_audio import SAMPLE_RATE, ULAW_SILENCE, apply_volume

logger = logging.getLogger("SentinelAudioBus")

FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000          # 160 campioni
FRAME_BYTES = FRAME_SAMPLES                              # mu-law: 1 byte per campione
SILENCE_FRAME = bytes([ULAW_SILENCE]) * FRAME_BYTES
RTP_PAYLOAD_TYPE_PCMU = 0
MAX_QUEUE = 8
# Oltre questo ritardo (thread sospeso, CPU satura) si riallinea il clock invece
# di inviare a raffica i pacchetti arretrati, che il Fanvil scarterebbe.
MAX_LATENESS_S = 0.2


class Priority(IntEnum):
    """Priorita' degli annunci: il valore piu' alto interrompe il piu' basso."""
    MANUAL = 10     # comandi manuali / dimostrazioni
    THOUGHT = 20    # frase contestuale di ORIN (Livello 1)
    REFLEX = 30     # riflesso immediato (Livello 0)
    ALARM = 40      # allarmi registrati (intrusione, urla, targhe)
    TAMPER = 50     # manomissione / sabotaggio


@dataclass
class _Clip:
    audio: bytes
    priority: Priority
    label: str
    requested_at: float = field(default_factory=time.monotonic)
    aborted: bool = False
    done: threading.Event = field(default_factory=threading.Event)


class AudioBus:
    """Trasmettitore RTP multicast con coda a priorita' verso il Fanvil A233."""

    def __init__(
        self,
        multicast_ip: Optional[str] = None,
        multicast_port: Optional[int] = None,
        iface_ip: Optional[str] = None,
        ttl: Optional[int] = None,
        preroll_ms: Optional[int] = None,
        hold_ms: Optional[int] = None,
    ):
        self.multicast_ip = multicast_ip or os.environ.get("FANVIL_MULTICAST_IP", "239.255.1.1")
        self.multicast_port = int(multicast_port or os.environ.get("FANVIL_MULTICAST_PORT", "5004"))
        self.iface_ip = iface_ip if iface_ip is not None else os.environ.get("FANVIL_MULTICAST_IFACE_IP", "").strip()
        self.ttl = int(ttl if ttl is not None else os.environ.get("FANVIL_MULTICAST_TTL", "16"))
        self.preroll_ms = int(preroll_ms if preroll_ms is not None else os.environ.get("FANVIL_RTP_DELAY_MS", "300"))
        self.hold_ms = int(hold_ms if hold_ms is not None else os.environ.get("FANVIL_RTP_HOLD_MS", "0"))

        self._cond = threading.Condition()
        self._queue: List[_Clip] = []
        self._current: Optional[_Clip] = None
        self._sock = self._open_socket()

        # Stato RTP
        self._ssrc = random.getrandbits(32)
        self._seq = random.getrandbits(16)
        self._timestamp = random.getrandbits(32)
        self._marker = False
        self._next_send = 0.0
        self._last_send = 0.0

        self._thread = threading.Thread(target=self._run, name="FanvilAudioBus", daemon=True)
        self._thread.start()

        logger.info(
            "AudioBus attivo -> rtp://%s:%d (G.711 mu-law, %d ms/pacchetto, pre-roll %d ms, hold %d ms, interfaccia %s)",
            self.multicast_ip, self.multicast_port, FRAME_MS, self.preroll_ms, self.hold_ms,
            self.iface_ip or "instradamento di sistema"
        )

    # ──────────────────────────────────────────────────────────────────────
    # API pubblica
    # ──────────────────────────────────────────────────────────────────────
    def play(
        self,
        audio: bytes,
        priority: Priority,
        label: str,
        volume_percent: Optional[float] = None,
        queue: bool = False,
    ) -> bool:
        """
        Consegna un buffer mu-law (8 kHz mono) all'altoparlante.
        Restituisce True se l'annuncio e' stato accettato (in onda o in coda).
        """
        if not audio:
            logger.warning("AudioBus: annuncio '%s' vuoto, ignorato.", label)
            return False
        if self._sock is None:
            logger.error("AudioBus: socket multicast non disponibile, annuncio '%s' non diffuso.", label)
            return False
        if volume_percent is not None:
            audio = apply_volume(audio, volume_percent)

        clip = _Clip(audio=audio, priority=Priority(priority), label=label)
        with self._cond:
            busy = self._current if self._current and not self._current.aborted else None
            highest_queued = self._queue[0] if self._queue else None
            top = busy or highest_queued

            if top is None:
                self._queue.append(clip)
            elif clip.priority > top.priority:
                # Interruzione: scarta quanto e' in onda e tutto cio' che in coda vale meno.
                if busy:
                    busy.aborted = True
                    logger.info("AudioBus: '%s' (%s) interrompe '%s' (%s).",
                                label, clip.priority.name, busy.label, busy.priority.name)
                for dropped in [c for c in self._queue if c.priority < clip.priority]:
                    dropped.aborted = True
                    dropped.done.set()
                self._queue = [c for c in self._queue if c.priority >= clip.priority]
                self._queue.insert(0, clip)
            elif queue and len(self._queue) < MAX_QUEUE:
                # Coda ordinata per priorita' decrescente, FIFO a parita' di priorita'.
                idx = len(self._queue)
                while idx > 0 and self._queue[idx - 1].priority < clip.priority:
                    idx -= 1
                self._queue.insert(idx, clip)
            else:
                logger.info("AudioBus: '%s' (%s) SCARTATO, canale occupato da '%s' (%s).",
                            label, clip.priority.name, top.label, top.priority.name)
                return False
            self._cond.notify()
        return True

    def stop(self):
        """Interrompe l'annuncio in corso e svuota la coda."""
        with self._cond:
            if self._current:
                self._current.aborted = True
            for clip in self._queue:
                clip.aborted = True
                clip.done.set()
            self._queue.clear()
            self._cond.notify()

    def is_playing(self) -> bool:
        """True se un annuncio e' in onda o in attesa di esserlo."""
        with self._cond:
            return bool(self._queue) or (self._current is not None and not self._current.aborted)

    # ──────────────────────────────────────────────────────────────────────
    # Trasmissione RTP
    # ──────────────────────────────────────────────────────────────────────
    def _open_socket(self) -> Optional[socket.socket]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self.ttl)
            if self.iface_ip:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.iface_ip))
            return sock
        except OSError as exc:
            logger.error("AudioBus: impossibile aprire il socket multicast (%s).", exc)
            return None

    def _send_frame(self, payload: bytes):
        """Invia un pacchetto RTP da 20 ms rispettando la cadenza in tempo reale."""
        now = time.monotonic()
        wait = self._next_send - now
        if wait > 0:
            time.sleep(wait)
        elif -wait > MAX_LATENESS_S:
            self._next_send = now

        header = struct.pack(
            "!BBHII",
            0x80,                                                   # V=2, P=0, X=0, CC=0
            (0x80 if self._marker else 0x00) | RTP_PAYLOAD_TYPE_PCMU,
            self._seq,
            self._timestamp,
            self._ssrc,
        )
        try:
            self._sock.sendto(header + payload, (self.multicast_ip, self.multicast_port))
        except OSError as exc:
            logger.warning("AudioBus: invio RTP fallito (%s).", exc)

        self._marker = False
        self._seq = (self._seq + 1) & 0xFFFF
        self._timestamp = (self._timestamp + FRAME_SAMPLES) & 0xFFFFFFFF
        self._next_send += FRAME_MS / 1000.0
        self._last_send = time.monotonic()

    def _start_talkspurt(self):
        """Apre una nuova sequenza parlata: marker, timestamp riallineato e pre-roll."""
        now = time.monotonic()
        if self._last_send:
            # Il timestamp RTP avanza anche durante il silenzio non trasmesso (RFC 3550).
            elapsed = int((now - self._last_send) * SAMPLE_RATE)
            self._timestamp = (self._timestamp + elapsed - elapsed % FRAME_SAMPLES) & 0xFFFFFFFF
        self._marker = True
        self._next_send = now
        for _ in range(self.preroll_ms // FRAME_MS):
            self._send_frame(SILENCE_FRAME)

    def _play_clip(self, clip: _Clip):
        first = True
        audio = clip.audio
        for offset in range(0, len(audio), FRAME_BYTES):
            if clip.aborted:
                logger.info("AudioBus: '%s' interrotto.", clip.label)
                break
            frame = audio[offset:offset + FRAME_BYTES]
            if len(frame) < FRAME_BYTES:
                frame += bytes([ULAW_SILENCE]) * (FRAME_BYTES - len(frame))
            self._send_frame(frame)
            if first:
                first = False
                logger.info(
                    "AudioBus: IN ONDA '%s' (%s) a %.0f ms dalla richiesta | durata %.1f s",
                    clip.label, clip.priority.name,
                    (time.monotonic() - clip.requested_at) * 1000.0,
                    len(audio) / SAMPLE_RATE
                )
        clip.done.set()

    def _take_next(self, hold_until: Optional[float]) -> Optional[_Clip]:
        """
        Restituisce il prossimo annuncio. Durante il periodo di hold trasmette
        silenzio per tenere aperto il canale; restituisce None quando l'hold scade.
        Con hold_until=None attende senza limiti (canale chiuso).
        """
        while True:
            with self._cond:
                if self._queue:
                    self._current = self._queue.pop(0)
                    return self._current
                self._current = None
                if hold_until is None:
                    self._cond.wait()
                    continue
                if time.monotonic() >= hold_until:
                    return None
            self._send_frame(SILENCE_FRAME)

    def _run(self):
        while True:
            try:
                clip = self._take_next(hold_until=None)
                self._start_talkspurt()
                while clip is not None:
                    self._play_clip(clip)
                    hold_until = time.monotonic() + self.hold_ms / 1000.0
                    clip = self._take_next(hold_until=hold_until)
            except Exception as exc:
                logger.exception("AudioBus: errore imprevisto nel ciclo di trasmissione: %s", exc)
                time.sleep(0.5)


# ──────────────────────────────────────────────────────────────────────────────
# Istanza unica per processo
# ──────────────────────────────────────────────────────────────────────────────
_bus_instance: Optional[AudioBus] = None
_bus_lock = threading.Lock()


def get_audio_bus(multicast_ip: Optional[str] = None, multicast_port: Optional[int] = None) -> AudioBus:
    """
    Restituisce l'AudioBus del processo, creandolo al primo utilizzo.
    I parametri valgono solo alla creazione; in loro assenza si usano le variabili d'ambiente.
    """
    global _bus_instance
    with _bus_lock:
        if _bus_instance is None:
            _bus_instance = AudioBus(multicast_ip=multicast_ip, multicast_port=multicast_port)
        return _bus_instance
