#!/bin/bash
# ==============================================================================
# CONF-LAVORO // ORIN — Ritorno alla versione più recente (main)
# ==============================================================================

echo "======================================================================"
echo ">>> RITORNO AL RAMO PRINCIPALE (MAIN - BIOMETRIA ORIN)"
echo "======================================================================"

git checkout main
git pull origin main

echo ""
echo ">>> STATO ATTUALE: Sei su main con il modulo di Registrazione Biometrica ORIN attivo."
echo "======================================================================"
