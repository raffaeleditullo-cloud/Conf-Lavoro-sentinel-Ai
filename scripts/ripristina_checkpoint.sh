#!/bin/bash
# ==============================================================================
# CONF-LAVORO // ORIN — Script di Ripristino Rapido al Checkpoint Stabile v1.3.2
# Permette ad Alessio o all'operatore di tornare istantaneamente alla versione
# precedente certificata (Video Wall Fluido + Health Check Reale) con un solo comando.
# ==============================================================================

echo "======================================================================"
echo ">>> RIPRISTINO AL CHECKPOINT STABILE v1.3.2"
echo "======================================================================"

# Salva eventuali file locali non committati in stash
git stash push -m "Auto-stash prima di ripristino checkpoint v1.3.2" 2>/dev/null

# Checkout del tag certificato
git checkout v1.3.2-stable-checkpoint

echo ""
echo ">>> STATO ATTUALE: Sei sul Checkpoint Stabile v1.3.2."
echo ">>> Tutte le funzionalità del Video Wall fluido e Health Check sono attive."
echo ">>> Per tornare alla versione con Biometria, lancia: ./scripts/torna_a_main.sh"
echo "======================================================================"
