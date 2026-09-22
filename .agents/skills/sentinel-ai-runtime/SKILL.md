---
name: sentinel-ai-runtime
description: >-
  Guida operativa e knowledge-base permanente per Conf-Lavoro Sentinel AI.
  Documenta l'architettura collaudata su Jetson Orin Nano, le configurazioni Frigate 0.17.2,
  i protocolli low-latency (RTSP vs HTTP-FLV Reolink), i parametri di rilevamento, i filtri anti-fantasma,
  la dissuasione vocale Fanvil RTP e la procedura di manutenzione e deploy.
---

# CONF-LAVORO SENTINEL AI — Architettura & Runtime Runbook

Questo documento funge da knowledge-base certificata per l'ambiente di produzione di Sentinel AI su **Jetson Orin Nano Super Dev Kit (8GB)**.

---

## 1. Topologia di Rete e Dispositivi Hardware

| Dispositivo | Indirizzo IP / Porta | Protocollo | Ruolo / Note |
|---|---|---|---|
| **Jetson Orin Nano** | `192.168.1.10` | SSH / Host network | Nodo di calcolo Edge (Frigate, TensorRT, Orchestrator, Dashboard) |
| **Cam Varco Carrabile** | `192.168.1.20` | RTSP (:554) / HTTP (:80) / RTMP (:1935) | Reolink RLC-811A 4K (Main 4K, Sub 640x360) |
| **Cam Varco Pedonale** | `192.168.1.21` | RTSP (:554) / HTTP (:80) / RTMP (:1935) | Reolink RLC-811A 4K (Main 4K, Sub 640x360) |
| **Cam Piazzale** | `192.168.1.22` | RTSP (:554) / HTTP (:80) / RTMP (:1935) | Reolink RLC-811A 4K (Main 4K, Sub 640x360) |
| **Relè Waveshare** | `192.168.1.30:4196` | Modbus TCP (Porta 4196) | Ch 1: Faretto 220V (30s) \| Ch 2: Cancello Carrabile (3s) |
| **Altoparlante Fanvil A233** | `192.168.1.31` | Multicast RTP `239.255.1.1:5004` | Codec G.711 µ-law mono, pre-roll 150ms |
| **NAS Ugreen** | `192.168.1.11` | SMB / CIFS (`sentinel-eventi`) | Archiviazione automatica snapshot e clip MP4 |

---

## 2. Regole d'Oro di Configurazione (Hard Rules)

1. **Preset Frigate su Jetson:**
   - In `config/config.yml` sotto `ffmpeg.inputs`, usare **esclusivamente**:
     ```yaml
     input_args: preset-rtsp-restream
     ```
   - ⚠️ **MAI aggiungere flag supplementari** a un preset (es. `preset-rtsp-restream -fflags nobuffer...` crasha NVDEC con `NvMMLiteOpen Block 261`).
2. **Detection FPS & TensorRT:**
   - `fps: 10` sulle 3 telecamere.
   - Il detector TensorRT gira a **~33.9ms** di tempo d'inferenza (consumo CPU/GPU ottimale).
   - Non abbassare `min_initialized: 2`, `threshold: 0.75`, `min_score: 0.60`.
3. **Threading per Attuatori:**
   - In `orchestrator/observer.py`, qualsiasi comando di attuazione verso hardware TCP (Relè Modbus) **deve essere eseguito in un thread separato** (`threading.Thread(daemon=True)`), per non bloccare mai il loop principale MQTT.

---

## 3. Algoritmi Anti-Fantasma (Filtri Decision Maker)

### Pezzettino 1: Filtro Sagome Proporzioni Umane (`HUMAN_RATIO_FILTER_ENABLED=true`)
- Un essere umano in piedi o che cammina ha un aspect ratio $H/W \ge 1.20$ (tipico $1.8 \div 2.8$).
- Forme con $H/W < 1.20$ (sedie, scatole, ombre a terra, riflessi) vengono scartate prima del trigger audio.
- Oggetti con area $> 45\%$ dello schermo (a ridosso della lente) vengono ignorati.

### Pezzettino 2: Filtro Movimento Dinamico & Traiettoria (`MOVEMENT_FILTER_ENABLED=true`)
- Mantiene in cache la traiettoria euclidea dei centroidi $[cx, cy]$ per ogni `track_id`.
- Se una sagoma è statica o compie oscillazioni minime ($< 2.5\%$ dello schermo) per $\ge 3$ update, il trigger audio ripetuto viene soppresso.

---

## 4. Dissuasione Vocale Sprint & Latenze Collaudate

- **File Audio Sprint:** `orchestrator/audio/carmelo/03_avviso_dissuasione.mp3` e `sami/03_avviso_dissuasione.mp3`
  - Durata: **2.1 secondi** (dimezzata rispetto ai 4.4s originari).
  - Testo: *"Alt! Area videosorvegliata. Allontanarsi immediatamente!"*
- **Latenza Software Misurata:**
  - Media tra **180ms e 300ms** dal momento della conferma di Frigate al comando audio.
- **Cooldown Globale Speaker:**
  - `SPEAKER_GLOBAL_COOLDOWN_SECONDS=20` (protegge dall'eco tra telecamere consecutive, lasciando la finestra aperta per un secondo intruso dopo 20s).

---

## 5. Comandi di Manutenzione Rapida sulla Jetson

```bash
# Entrare nella directory di lavoro
cd /home/alessio/sentinel-ai

# Aggiornamento ed esecuzione automatica
git pull
bash deploy_sprint.sh

# Monitoraggio in tempo reale dei log decisionali
docker compose logs -f orchestrator

# Ripristino configurazione di emergenza
bash deploy_sprint.sh --revert
```
