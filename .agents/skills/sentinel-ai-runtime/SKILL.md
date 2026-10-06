---
name: sentinel-ai-runtime
description: >-
  Guida operativa e knowledge-base permanente per Conf-Lavoro Sentinel AI.
  Documenta l'architettura collaudata su Jetson Orin Nano, le configurazioni Frigate 0.17.2,
  il motore di riflesso immediato R2-D2, l'AudioBus RTP Python nativo, VoiceArbiter,
  il Gate deterministico HEXAD DEMON, il verbalizzatore KERYX e il piano di interazione bidirezionale.
---

# CONF-LAVORO SENTINEL AI — Architettura & Knowledge-Base Permanente

Questo documento è la memoria tecnica certificata per l'ambiente di produzione di Sentinel AI su **Jetson Orin Nano Super Dev Kit (8GB)**.

---

## 1. Topologia di Rete e Dispositivi Hardware

| Dispositivo | Indirizzo IP / Porta | Protocollo | Ruolo / Note |
|---|---|---|---|
| **Jetson Orin Nano** | `192.168.1.10` | SSH / Host network | Nodo Edge (Frigate 0.17.2, TensorRT, Orchestrator, Dashboard) |
| **Cam Piazzale Esterno** | `192.168.1.22` | HTTP-FLV / RTSP (:554) | Reolink RLC-811A 4K (Main 4K, Sub 640x360, Mic integrato) |
| **Cam Magazzino Interno** | `192.168.1.20` | HTTP-FLV / RTSP (:554) | Reolink RLC-811A 4K (Main 4K, Sub 640x360, Mic integrato) |
| **Cam Corridoio Transito**| `192.168.1.21` | HTTP-FLV / RTSP (:554) | Reolink RLC-811A 4K (Main 4K, Sub 640x360, Mic integrato) |
| **Relè Waveshare** | `192.168.1.30:4196` | Modbus TCP (Porta 4196) | Ch 1: Faretto 220V (30s) \| Ch 2: Cancello Carrabile (3s) |
| **Altoparlante Fanvil A233** | `192.168.1.31` | Multicast RTP `239.255.1.1:5004` | Codec G.711 µ-law mono, pre-roll 250ms, hold 3000ms |
| **NAS Ugreen** | `192.168.1.11` | SMB / CIFS (`sentinel-eventi`) | Archiviazione automatica snapshot e clip MP4 |

---

## 2. Architettura Audio a Due Livelli ("R2-D2 Droide")

Per azzerare la latenza percepita (in precedenza 4-6 secondi), il sistema adotta un modello a riflesso e pensiero:

```
[Movimento Telecamera] 
         │
         ├──► (0.2s - 250ms)  L0 RIFLESSO LOCALE: AudioBus suona clip breve da RAM ("Attenzione, sei inquadrato")
         │
         └──► (2.0s - 2.8s)  L1 PENSIERO ORIN: Gemini Flash analizza la scena + ElevenLabs Flash v2.5 genera frase su misura
                                   │
                                   ▼
                              AudioBus aggancia la frase dell'AI senza pause sullo stesso canale
```

### Componenti Chiave:
1. **`orchestrator/ulaw_audio.py`**: Codec puro Python conforme ITU-T G.711 µ-law. Converte i suoni una volta sola all'avvio e li mantiene in RAM.
2. **`orchestrator/rtp_audio_bus.py`**: Unico proprietario dell'altoparlante Fanvil. Trasmette pacchetti RTP UDP multicast da 20ms (160 byte) direttamente da Python, eliminando per sempre i sottoprocessi `ffmpeg`.
   - Gerarchia di priorità: `TAMPER (50) > ALARM (40) > REFLEX (30) > THOUGHT (20) > MANUAL (10)`.
3. **`orchestrator/voice_arbiter.py`**: Risolve il blocco del cooldown vocale. Il riflesso e la frase contestuale di ORIN condividono lo stesso turno di parola: il riflesso parla e apre una finestra di ascolto garantita per ORIN.
4. **`orchestrator/reflex_engine.py`**: Gestisce la libreria di 20 frasi pre-sintetizzate (10 Carmelo + 10 Sami) suddivise per telecamera, orario (giorno/notte) e recidiva.
5. **`orchestrator/keryx_verbalizer.py`**: Motore fonetico e prosodico derivato da SKILL DEMON (conversione numeri in parole, riparazione accenti, virgole di respiro, mappatura acronimi tecnici).
6. **`orchestrator/demon_gate.py`**: Gate deterministico HEXAD. Impedisce ad allucinazioni VLM o spoofing visivo (es. foto mostrata alla lente) di aprire il cancello fisico. Verifica inoltre la lunghezza e conformità delle frasi parlate (PEIRA).

---

## 3. Gestione della Dashboard e Routing Centralizzato

- La Dashboard Web comunica con l'Orchestratore tramite il topic MQTT `sentinel/cmd/speaker/#` (con credenziali autenticate).
- I comandi manuali di dissuasione o test vocale vengono accodati all'AudioBus centrale con priorità, impedendo che due sorgenti parlino contemporaneamente sullo stesso canale multicast.
- L'analisi delle immagini da parte di ORIN è deduplicata (`_analyzed_events`): per ciascun intruso viene effettuata una sola chiamata a OpenRouter, abbattendo del 90% i costi API.

---

## 4. Roadmap Prossima Fase: Interazione Bidirezionale (Chat & Push-to-Talk)

### Fase A — Chat Testuale Operatore con l'Occhio Cibernetico ORIN:
- Direttamente dall'interfaccia Dashboard Web (accanto al feed telecamere):
- L'utente scrive un comando in linguaggio naturale (es. *"ORIN, chiedi al corriere per chi è il pacco"* oppure *"Avvisa di attendere due minuti"*).
- Gemini Flash riceve il comando + l'ultimo fotogramma della telecamera attiva, sintetizza la risposta appropriata ed ElevenLabs la pronuncia dal varco.
- Tempo di reazione stimato: **1.5 - 2.0 secondi**.

### Fase B — Push-to-Talk (Microfono da Smartphone/Browser):
- Pulsante microfono nell'interfaccia web.
- L'operatore tiene premuto, parla nel telefono e l'audio PCM/µ-law viene inviato direttamente in streaming al Fanvil A233.
- Tempo di reazione stimato: **< 200 millisecondi** (voce diretta in tempo reale).

### Fase C — Microfoni Reolink e Privacy:
- Le telecamere Reolink RLC-811A montano un microfono integrato sul flusso RTSP/FLV.
- Per conformità GDPR / Statuto Lavoratori, l'ascolto non è mai continuo (vietata intercettazione ambientale), ma si apre solo per 5-10 secondi a seguito di una domanda dell'AI.

---

## 5. Comandi di Manutenzione e Riavvio

```bash
cd ~/sentinel-ai
git pull
docker compose restart orchestrator dashboard
```

Verifica log in tempo reale:
```bash
docker compose logs -f --tail 20 orchestrator | grep -E "RIFLESSO|ORIN|AudioBus|Latenza"
```
