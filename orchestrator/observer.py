#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Orchestratore Osservatore (Fase 1 / Modalita' Diagnostica)

Ruolo:
- Connessione al broker MQTT locale (Mosquitto) con credenziali da ambiente.
- Sottoscrizione al wildcard topic 'frigate/#'.
- Registrazione degli eventi su file in formato JSON Lines (JSONL):
  - Ogni riga e' un oggetto JSON completo e indipendente, direttamente deserializzabile
    e "rigiocabile" (replay) nei test di sviluppo della Fase 2.
  - Campi garantiti: timestamp (ISO 8601 con fuso orario esplicito), topic, type (text, json, binary, truncated),
    payload_bytes, payload (annidato come dict nativo se JSON valido, stringa se testo ordinario, omesso se binario).
- Protezione da immagini JPEG grezze (es. frigate/<cam>/<obj>/snapshot):
  - Verifica UTF-8 rigorosa (strict): se fallisce, logga type="binary" senza dump dei byte.
- Troncamento di sicurezza per testi eccedenti MAX_TEXT_LENGTH caratteri.
- Rotazione automatica a 10 MB per file, max 5 backup storici (tetto massimo 50 MB su disco).
- Console stdout per Alessio via `docker compose logs -f orchestrator` in formato testuale sintetico.
- NESSUNA azione attiva: non comanda rele', non invia comandi SIP, non decide allarmi.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
import paho.mqtt.client as mqtt

# ──────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURAZIONE PARAMETRI DI RUNTIME
# ──────────────────────────────────────────────────────────────────────────────
MQTT_HOST = os.environ.get("FRIGATE_MQTT_HOST", "mosquitto")
MQTT_PORT = 1883  # Porta standard interna cablata coerentemente con config.yml
MQTT_USER = os.environ.get("FRIGATE_MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("FRIGATE_MQTT_PASSWORD", "")
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
LOG_FILE = os.path.join(LOG_DIR, "sentinel_events.log")

# Soglia massima di caratteri per payload testuale prima del troncamento di sicurezza
MAX_TEXT_LENGTH = 3000

# ──────────────────────────────────────────────────────────────────────────────
# 2. INIZIALIZZAZIONE LOGGERS
# ──────────────────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)

# Logger di sistema (operativo, diagnostico, console)
logger = logging.getLogger("SentinelObserver")
logger.setLevel(logging.INFO)

console_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Logger dedicato al file JSON Lines: scrive la stringa JSON grezza pura senza prefissi
jsonl_logger = logging.getLogger("SentinelEventLog")
jsonl_logger.setLevel(logging.INFO)
jsonl_logger.propagate = False  # Non duplica su stdout

file_formatter = logging.Formatter(fmt="%(message)s")
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,              # max 5 file = 50 MB totali
    encoding="utf-8"
)
file_handler.setFormatter(file_formatter)
jsonl_logger.addHandler(file_handler)

# ──────────────────────────────────────────────────────────────────────────────
# 3. CALLBACK MQTT — API VERSION2 (paho-mqtt >= 2.0.0)
# ──────────────────────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if not reason_code.is_failure:
        logger.info(
            "Connessione stabilita con successo al broker MQTT (%s:%d) [ReasonCode: %s]",
            MQTT_HOST, MQTT_PORT, reason_code
        )
        client.subscribe("frigate/#", qos=0)
        logger.info("Sottoscrizione attiva al wildcard topic 'frigate/#' — in ascolto...")
    else:
        logger.error(
            "Fallimento connessione al broker MQTT (%s:%d). Errore: %s",
            MQTT_HOST, MQTT_PORT, reason_code
        )

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    if reason_code.is_failure:
        logger.warning(
            "Disconnessione imprevista dal broker MQTT [ReasonCode: %s, Flags: %s]. Riconnessione in corso...",
            reason_code, disconnect_flags
        )
    else:
        logger.info("Disconnessione ordinaria dal broker MQTT [ReasonCode: %s]", reason_code)

def on_message(client, userdata, msg):
    topic = msg.topic
    raw_payload = msg.payload
    payload_len = len(raw_payload)

    # Orario in formato ISO 8601 con fuso orario esplicito (eredita TZ da container, es. +02:00)
    iso_timestamp = datetime.now(timezone.utc).astimezone().isoformat()

    # 1. Verifica binaria (UTF-8 strict)
    #    Scarta immagini JPEG grezze (es. frigate/<cam>/<obj>/snapshot) salvando solo i metadati
    try:
        text_payload = raw_payload.decode("utf-8")
        is_binary = False
    except UnicodeDecodeError:
        is_binary = True

    record = {
        "timestamp": iso_timestamp,
        "topic": topic,
        "payload_bytes": payload_len
    }

    if is_binary:
        record["type"] = "binary"
        # Omette il campo 'payload' per non inquinare il file con byte illeggibili
        logger.info("[EVENT-BIN] Topic: %s | Dimensione: %d byte", topic, payload_len)
    else:
        # 2. Verifica se il testo e' un JSON valido per annidarlo come dict nativo
        parsed_json = None
        if (text_payload.startswith("{") and text_payload.endswith("}")) or \
           (text_payload.startswith("[") and text_payload.endswith("]")):
            try:
                parsed_json = json.loads(text_payload)
            except Exception:
                parsed_json = None

        if parsed_json is not None:
            record["type"] = "json"
            record["payload"] = parsed_json
            logger.info("[EVENT-JSON] Topic: %s (%d byte)", topic, payload_len)
        else:
            # 3. Testo ordinario (es. "ON", "OFF", stringhe semplici) con controllo di lunghezza
            if len(text_payload) > MAX_TEXT_LENGTH:
                record["type"] = "truncated"
                record["payload"] = text_payload[:MAX_TEXT_LENGTH]
                record["original_length"] = len(text_payload)
                logger.info("[EVENT-TRUNC] Topic: %s (%d byte, troncato)", topic, payload_len)
            else:
                record["type"] = "text"
                record["payload"] = text_payload
                logger.info("[EVENT-TEXT] Topic: %s | Valore: %s", topic, text_payload)

    # Scrittura di una singola riga JSON (separatori compatti senza a capo interni)
    json_line = json.dumps(record, ensure_ascii=False, separators=(',', ':'))
    jsonl_logger.info(json_line)

# ──────────────────────────────────────────────────────────────────────────────
# 4. CICLO PRINCIPALE DI VITA DEL SERVIZIO
# ──────────────────────────────────────────────────────────────────────────────
def main():
    logger.info("════════════════════════════════════════════════════════════════════")
    logger.info("Avvio CONF-LAVORO Sentinel AI — Orchestratore Osservatore v1.0")
    logger.info("Broker target: %s:%d | Utente: %s", MQTT_HOST, MQTT_PORT, MQTT_USER)
    logger.info("Registro eventi (JSON Lines): %s", LOG_FILE)
    logger.info("Politica rotazione: 10 MB x 5 file backup (Max 50 MB)")
    logger.info("Fuso orario attivo: %s", os.environ.get("TZ", "Europe/Rome"))
    logger.info("════════════════════════════════════════════════════════════════════")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="sentinel_ai_observer"
    )

    if MQTT_USER and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # Riconnessione controllata con backoff esponenziale iniziale
    backoff = 2
    connected = False

    while not connected:
        try:
            logger.info("Tentativo di connessione al broker %s:%d...", MQTT_HOST, MQTT_PORT)
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            connected = True
        except Exception as err:
            logger.warning(
                "Broker MQTT non ancora disponibile (%s). Nuovo tentativo tra %d secondi...",
                err, backoff
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

    # Loop MQTT non-bloccante nativo di paho
    try:
        client.loop_forever(retry_first_connection=True)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Richiesta terminazione orchestratore. Disconnessione dal broker...")
        client.disconnect()
        logger.info("Orchestratore arrestato regolarmente.")

if __name__ == "__main__":
    main()
