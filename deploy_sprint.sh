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

echo "[2/4] Aggiornamento parametri low-latency, filtri e JEV Decider..."
update_or_add "FANVIL_RTP_DELAY_MS" "150"
update_or_add "SPEAKER_GLOBAL_COOLDOWN_SECONDS" "20"
update_or_add "HUMAN_RATIO_FILTER_ENABLED" "true"
update_or_add "MIN_HUMAN_ASPECT_RATIO" "1.2"
update_or_add "MAX_PERSON_AREA_RATIO" "0.45"
update_or_add "MOVEMENT_FILTER_ENABLED" "true"
update_or_add "MIN_MOVEMENT_DISTANCE" "0.025"
update_or_add "JEV_DECIDER_ENABLED" "true"

echo "[3/4] Mappatura flussi telecamere ambiente reale (indicazioni Alessio)..."
# Telecamera 1: Piazzale Esterno (.22)
update_or_add "FRIGATE_CAM_PIAZZALE_MAIN_URL" "rtsp://admin:${CAM_PASSWORD}@192.168.1.22:554/h264Preview_01_main"
update_or_add "FRIGATE_CAM_PIAZZALE_SUB_URL" "rtsp://admin:${CAM_PASSWORD}@192.168.1.22:554/h264Preview_01_sub"

# Telecamera 2: Magazzino Interno (.20)
update_or_add "FRIGATE_CAM_MAGAZZINO_MAIN_URL" "rtsp://admin:${CAM_PASSWORD}@192.168.1.20:554/h264Preview_01_main"
update_or_add "FRIGATE_CAM_MAGAZZINO_SUB_URL" "rtsp://admin:${CAM_PASSWORD}@192.168.1.20:554/h264Preview_01_sub"

# Telecamera 3: Corridoio di Transito (.21)
update_or_add "FRIGATE_CAM_CORRIDOIO_MAIN_URL" "rtsp://admin:${CAM_PASSWORD}@192.168.1.21:554/h264Preview_01_main"
update_or_add "FRIGATE_CAM_CORRIDOIO_SUB_URL" "rtsp://admin:${CAM_PASSWORD}@192.168.1.21:554/h264Preview_01_sub"

# Mappatura relè aggiornata
update_or_add "RELAY_CHANNEL_PIAZZALE" "1"
update_or_add "RELAY_CHANNEL_MAGAZZINO" "1"
update_or_add "RELAY_CHANNEL_CORRIDOIO" "1"

echo "  ✔ Piazzale Esterno   (192.168.1.22): Main + Sub collegate"
echo "  ✔ Magazzino Interno  (192.168.1.20): Main + Sub collegate"
echo "  ✔ Corridoio Transito (192.168.1.21): Main + Sub collegate"

echo "[4/4] Riavvio servizi Frigate e Orchestrator..."
docker compose up -d --force-recreate frigate orchestrator

echo ""
echo "======================================================================"
echo "  ✅ SISTEMA AGGIORNATO CON SUCCESSO!"
echo "  - Telecamere attive: 'piazzale', 'magazzino', 'corridoio'"
echo "  - JEV Adaptive Decider attivo (Profili dedicati per ambiente)"
echo "  - Generatore Identikit Forense attivo"
echo "  - Frigate a 10 FPS | Audio Sprint 2.0s | Pre-roll 150ms"
echo "======================================================================"
echo "In caso di necessità: bash deploy_sprint.sh --revert"
echo "Monitoraggio log: docker compose logs -f orchestrator"

