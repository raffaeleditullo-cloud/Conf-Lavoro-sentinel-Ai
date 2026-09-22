#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# CONF-LAVORO SENTINEL AI — DEPLOYMENT COMPLETO: SPRINT + PEZZETTINO 2 + HTTP-FLV
# ══════════════════════════════════════════════════════════════════════════════
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE=".env"
BAK_FILE=".env.bak"

echo "======================================================================"
echo "  SENTINEL AI — ULTRA-LOW-LATENCY PIPELINE DEPLOYMENT"
echo "  (Audio Sprint + Pezzettino 2 + HTTP-FLV su tutte e 3 le Cam)"
echo "======================================================================"

# Opzione revert
if [ "$1" == "--revert" ]; then
    if [ -f "$BAK_FILE" ]; then
        echo "Ripristino configurazione precedente da $BAK_FILE..."
        cp "$BAK_FILE" "$ENV_FILE"
        docker compose up -d --force-recreate frigate orchestrator
        echo "✅ Configurazione ripristinata con successo!"
        exit 0
    else
        echo "❌ Nessun backup $BAK_FILE trovato!"
        exit 1
    fi
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Errore: file $ENV_FILE non trovato in $SCRIPT_DIR!"
    exit 1
fi

# 1. Backup di sicurezza
cp "$ENV_FILE" "$BAK_FILE"
echo "[1/4] Creato backup di sicurezza in $BAK_FILE"

# 2. Estrazione password telecamere Reolink dal file attuale
CAM_PASSWORD=""
# Cerca prima password da URL rtsp://admin:PWD@...
if grep -q "rtsp://admin:" "$ENV_FILE"; then
    CAM_PASSWORD=$(grep "rtsp://admin:" "$ENV_FILE" | head -n 1 | sed -n 's/.*rtsp:\/\/admin:\([^@]*\)@.*/\1/p')
fi
# Se non trovata o era già in formato http, cerca password=...
if [ -z "$CAM_PASSWORD" ] && grep -q "password=" "$ENV_FILE"; then
    CAM_PASSWORD=$(grep "password=" "$ENV_FILE" | head -n 1 | sed -n 's/.*password=\([^&# ]*\).*/\1/p')
fi
# Se ancora vuota cerca nel campo REOLINK_PASSWORD
if [ -z "$CAM_PASSWORD" ] && grep -q "^REOLINK_PASSWORD=" "$ENV_FILE"; then
    CAM_PASSWORD=$(grep "^REOLINK_PASSWORD=" "$ENV_FILE" | head -n 1 | cut -d'=' -f2-)
fi

if [ -z "$CAM_PASSWORD" ]; then
    echo "⚠️ Impossibile rilevare automaticamente la password telecamera dal .env."
    read -r -p "Inserisci la password delle telecamere Reolink: " CAM_PASSWORD
fi

echo "  ✔ Password telecamere rilevata."

# 3. Funzione per aggiornare o aggiungere chiavi nel .env
update_or_add() {
    local key="$1"
    local val="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        # Usa delimitatore pipe per evitare problemi con slash
        sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else
        echo "${key}=${val}" >> "$ENV_FILE"
    fi
}

echo "[2/4] Aggiornamento parametri low-latency e Pezzettino 2..."
update_or_add "FANVIL_RTP_DELAY_MS" "150"
update_or_add "SPEAKER_GLOBAL_COOLDOWN_SECONDS" "20"
update_or_add "HUMAN_RATIO_FILTER_ENABLED" "true"
update_or_add "MIN_HUMAN_ASPECT_RATIO" "1.2"
update_or_add "MAX_PERSON_AREA_RATIO" "0.45"
update_or_add "MOVEMENT_FILTER_ENABLED" "true"
update_or_add "MIN_MOVEMENT_DISTANCE" "0.025"

echo "[3/4] Configurazione flussi HTTP-FLV zero-latency su tutte e 3 le telecamere..."
# Telecamera 1: Varco Carrabile (.20)
update_or_add "FRIGATE_CAM_VARCO_CARRABILE_MAIN_URL" "ffmpeg:http://admin:${CAM_PASSWORD}@192.168.1.20/flv?port=1935\&app=bcs\&stream=channel0_main.bcs#video=copy#audio=copy"
update_or_add "FRIGATE_CAM_VARCO_CARRABILE_SUB_URL" "ffmpeg:http://admin:${CAM_PASSWORD}@192.168.1.20/flv?port=1935\&app=bcs\&stream=channel0_sub.bcs#video=copy"

# Telecamera 2: Varco Pedonale (.21)
update_or_add "FRIGATE_CAM_VARCO_PEDONALE_MAIN_URL" "ffmpeg:http://admin:${CAM_PASSWORD}@192.168.1.21/flv?port=1935\&app=bcs\&stream=channel0_main.bcs#video=copy#audio=copy"
update_or_add "FRIGATE_CAM_VARCO_PEDONALE_SUB_URL" "ffmpeg:http://admin:${CAM_PASSWORD}@192.168.1.21/flv?port=1935\&app=bcs\&stream=channel0_sub.bcs#video=copy"

# Telecamera 3: Piazzale (.22)
update_or_add "FRIGATE_CAM_PIAZZALE_MAIN_URL" "ffmpeg:http://admin:${CAM_PASSWORD}@192.168.1.22/flv?port=1935\&app=bcs\&stream=channel0_main.bcs#video=copy#audio=copy"
update_or_add "FRIGATE_CAM_PIAZZALE_SUB_URL" "ffmpeg:http://admin:${CAM_PASSWORD}@192.168.1.22/flv?port=1935\&app=bcs\&stream=channel0_sub.bcs#video=copy"

echo "  ✔ Varco Carrabile (192.168.1.20): Main + Sub -> HTTP-FLV"
echo "  ✔ Varco Pedonale  (192.168.1.21): Main + Sub -> HTTP-FLV"
echo "  ✔ Piazzale        (192.168.1.22): Main + Sub -> HTTP-FLV"

echo "[4/4] Riavvio servizi Frigate e Orchestrator..."
docker compose up -d --force-recreate frigate orchestrator

echo ""
echo "======================================================================"
echo "  ✅ SISTEMA ATTIVATO IN MODALITÀ ZERO-LATENCY!"
echo "  - Tutte e 3 le telecamere collegate in HTTP-FLV (addio buffer RTSP)"
echo "  - Frigate attivo a 10 FPS"
echo "  - Audio Sprint 2.0s attivo"
echo "  - Pre-roll Fanvil a 150ms"
echo "  - Filtri Sagome & Movimento Dinamico attivi"
echo "======================================================================"
echo "In caso di necessità per tornare a RTSP: bash deploy_sprint.sh --revert"
echo "Monitoraggio log: docker compose logs -f orchestrator"
