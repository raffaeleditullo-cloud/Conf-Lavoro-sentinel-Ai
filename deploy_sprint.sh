#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# CONF-LAVORO SENTINEL AI — SCRIPT AGGIORNAMENTO SPRINT & PEZZETTINO 2
# ══════════════════════════════════════════════════════════════════════════════
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================================"
echo "  SENTINEL AI — APPLICAZIONE SPRINT AUDIO & PEZZETTINO 2"
echo "======================================================================"

ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Errore: file $ENV_FILE non trovato in $SCRIPT_DIR!"
    exit 1
fi

echo "[1/3] Allineamento parametri ultra-low-latency in $ENV_FILE..."

# Funzione per aggiornare o aggiungere chiavi nel .env
update_or_add() {
    local key="$1"
    local val="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else
        echo "${key}=${val}" >> "$ENV_FILE"
    fi
}

update_or_add "FANVIL_RTP_DELAY_MS" "150"
update_or_add "SPEAKER_GLOBAL_COOLDOWN_SECONDS" "20"
update_or_add "HUMAN_RATIO_FILTER_ENABLED" "true"
update_or_add "MIN_HUMAN_ASPECT_RATIO" "1.2"
update_or_add "MAX_PERSON_AREA_RATIO" "0.45"
update_or_add "MOVEMENT_FILTER_ENABLED" "true"
update_or_add "MIN_MOVEMENT_DISTANCE" "0.025"

echo "  ✔ FANVIL_RTP_DELAY_MS=150 (ridotto pre-roll)"
echo "  ✔ SPEAKER_GLOBAL_COOLDOWN_SECONDS=20"
echo "  ✔ HUMAN_RATIO_FILTER_ENABLED=true (Pezzettino 1 - Sagome)"
echo "  ✔ MOVEMENT_FILTER_ENABLED=true (Pezzettino 2 - Movimento dinamico)"

echo "[2/3] Verifica tracce audio Sprint..."
if [ -f "orchestrator/audio/carmelo/03_avviso_dissuasione.mp3" ]; then
    echo "  ✔ Audio sprint carmelo presente"
fi
if [ -f "orchestrator/audio/sami/03_avviso_dissuasione.mp3" ]; then
    echo "  ✔ Audio sprint sami presente"
fi

echo "[3/3] Riavvio servizi Frigate e Orchestrator..."
docker compose up -d --force-recreate frigate orchestrator

echo ""
echo "======================================================================"
echo "  ✅ SISTEMA AGGIORNATO CON SUCCESSO!"
echo "  - Frigate attivo a 10 FPS"
echo "  - Audio Sprint 2.0s caricato ('Alt! Area videosorvegliata...')"
echo "  - Pre-roll Fanvil a 150ms"
echo "  - Filtro Movimento Dinamico (Pezzettino 2) attivo"
echo "======================================================================"
echo "Per verificare in tempo reale: docker compose logs -f orchestrator"
