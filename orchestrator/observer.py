#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Orchestratore Osservatore (Fase 1 / Modalita' Diagnostica)

Ruolo:
- Connessione al broker MQTT locale (Mosquitto) con credenziali da ambiente.
- Sottoscrizione al wildcard topic 'frigate/#'.
- Protezione del registro da payload binari (es. snapshot JPEG su frigate/<cam>/<obj>/snapshot):
  - Verifica UTF-8 rigorosa (strict): se fallisce, logga solo topic e dimensione byte.
  - Troncatura controllata dei messaggi testuali superiori a MAX_TEXT_LENGTH caratteri.
- Scrittura di ogni evento in formato strutturato su file di log rotante:
  - Rotazione automatica a 10 MB per file, max 5 backup storici (max 50 MB totali su disco).
  - Riconnessione esponenziale automatica in caso di caduta del broker senza inondare i log.
- NESSUNA azione attiva: non comanda rele', non invia comandi SIP, non decide allarmi.
"""

import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
import paho.mqtt.client as mqtt

# ──────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURAZIONE PARAMETRI DI RUNTIME
# ──────────────────────────────────────────────────────────────────────────────
# In Frigate e Mosquitto la porta 1883 e' standard interno alla rete Docker.
# Uniformata la convenzione: host, user e password provengono dalle variabili FRIGATE_*.
MQTT_HOST = os.environ.get("FRIGATE_MQTT_HOST", "mosquitto")
MQTT_PORT = 1883  # Porta standard interna cablata coerentemente con config.yml
MQTT_USER = os.environ.get("FRIGATE_MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("FRIGATE_MQTT_PASSWORD", "")
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
LOG_FILE = os.path.join(LOG_DIR, "sentinel_events.log")

# Soglia massima di caratteri per payload testuale prima del troncamento di sicurezza
MAX_TEXT_LENGTH = 3000

# ──────────────────────────────────────────────────────────────────────────────
# 2. INIZIALIZZAZIONE LOGGER ROTANTE
# ──────────────────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("SentinelObserver")
logger.setLevel(logging.INFO)

# Formattatore: Data e ora precisa (fuso locale tramite tzdata + TZ), livello e messaggio
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Handler rotante su file: 10 MB per file, max 5 backup storici (tetto massimo: 50 MB)
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler stdout su console (visibile via `docker compose logs -f orchestrator`)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ──────────────────────────────────────────────────────────────────────────────
# 3. CALLBACK MQTT — API VERSION2 (paho-mqtt >= 2.0.0)
# Documentazione: https://github.com/eclipse-paho/paho.mqtt.python
# In CallbackAPIVersion.VERSION2:
#   - on_connect:    (client, userdata, flags, reason_code, properties)
#   - on_disconnect: (client, userdata, disconnect_flags, reason_code, properties)
#   - reason_code:   istanza di paho.mqtt.reasoncodes.ReasonCode
#                    (ha il metodo reason_code.is_failure per valutare l'esito)
# ──────────────────────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if not reason_code.is_failure:
        logger.info(
            "Connessione stabilita con successo al broker MQTT (%s:%d) [ReasonCode: %s]",
            MQTT_HOST, MQTT_PORT, reason_code
        )
        # Sottoscrizione all'intero albero di eventi di Frigate
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

    # 1. Verifica rigorosa se il payload e' testo valido (UTF-8 strict)
    #    Scarta immagini JPEG binarie (es. frigate/<cam>/<obj>/snapshot) evitando caratteri spuri nel log.
    try:
        text_payload = raw_payload.decode("utf-8")
        is_binary = False
    except UnicodeDecodeError:
        is_binary = True

    if is_binary:
        logger.info(
            "[EVENT-BIN] Topic: %s | [contenuto binario non stampato, dimensione: %d byte]",
            topic, payload_len
        )
        return

    # 2. Controllo e troncamento di sicurezza sulla lunghezza del testo
    if len(text_payload) > MAX_TEXT_LENGTH:
        truncated_text = text_payload[:MAX_TEXT_LENGTH]
        logger.info(
            "[EVENT-TRUNC] Topic: %s | [lunghezza originale: %d caratteri, troncato a %d]: %s... [TRONCATO]",
            topic, len(text_payload), MAX_TEXT_LENGTH, truncated_text
        )
    else:
        logger.info("[EVENT] Topic: %s | Payload: %s", topic, text_payload)

# ──────────────────────────────────────────────────────────────────────────────
# 4. CICLO PRINCIPALE DI VITA DEL SERVIZIO
# ──────────────────────────────────────────────────────────────────────────────
def main():
    logger.info("════════════════════════════════════════════════════════════════════")
    logger.info("Avvio CONF-LAVORO Sentinel AI — Orchestratore Osservatore v1.0")
    logger.info("Broker target: %s:%d | Utente: %s", MQTT_HOST, MQTT_PORT, MQTT_USER)
    logger.info("Destinazione registro eventi: %s (Rotazione: 10MB x 5 backup)", LOG_FILE)
    logger.info("Fuso orario configurato: %s", os.environ.get("TZ", "UTC"))
    logger.info("════════════════════════════════════════════════════════════════════")

    # Inizializzazione client Paho MQTT con API VERSION2 formale
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
