# CHECKLIST DI COLLAUDO — Sentinel AI v1

Eseguire questa checklist **in campo** con il sistema avviato e le telecamere
montate nella posizione definitiva. Ogni voce va verificata e spuntata.

**Data collaudo**: _______________
**Eseguito da**: _______________

---

## Sezione 1 — Infrastruttura e Sicurezza Rete

| # | Verifica | Esito atteso | ✓ | Note |
|:-:|----------|-------------|:-:|------|
| 1.1 | Container Frigate in esecuzione e sano | `docker compose ps` → `frigate Up (healthy)` | ☐ | |
| 1.2 | Container Mosquitto in esecuzione | `docker compose ps` → `mosquitto Up` | ☐ | |
| 1.3 | Container Orchestrator in esecuzione | `docker compose ps` → `orchestrator Up` | ☐ | |
| 1.4 | Interfaccia protetta Frigate raggiungibile | Browser → `https://IP_JETSON:8971` → schermata di login | ☐ | |
| 1.5 | **Sicurezza: porta 5000 NON esposta sulla LAN** | Da altro PC sulla LAN: `http://IP_JETSON:5000` deve dare **Connessione rifiutata** | ☐ | |
| 1.6 | Modello TensorRT generato | File presente in `config/model_cache/tensorrt/yolov4-416.trt` | ☐ | |
| 1.7 | Credenziali admin recuperate e modificate | Accesso eseguito con password generata e modificata in Settings | ☐ | |
| 1.8 | Autenticazione MQTT funzionante | `docker compose logs mosquitto` → nessun `Connection Refused` | ☐ | |
| 1.9 | Spazio disco SSD sufficiente | `df -h /mnt/storage` → almeno 700 GB liberi | ☐ | |



---

## Sezione 2 — Flussi Video

| # | Verifica | Esito atteso | ✓ | Note |
|:-:|----------|-------------|:-:|------|
| 2.1 | Varco Carrabile — video live | Flusso visibile nell'interfaccia Frigate | ☐ | |
| 2.2 | Varco Pedonale — video live | Flusso visibile nell'interfaccia Frigate | ☐ | |
| 2.3 | Piazzale — video live | Flusso visibile nell'interfaccia Frigate | ☐ | |
| 2.4 | Nessun flusso con "errore decodifica" | Nessun messaggio `error` nei log FFmpeg | ☐ | |
| 2.5 | Risoluzione sub-stream corretta | Debug → Detect → risoluzione `640×360` per tutte | ☐ | |

---

## Sezione 3 — Rilevamento Oggetti

| # | Verifica | Esito atteso | ✓ | Note |
|:-:|----------|-------------|:-:|------|
| 3.1 | Persona rilevata — Varco Pedonale | Persona cammina davanti alla telecamera → riquadro verde `person` | ☐ | |
| 3.2 | Persona rilevata — Piazzale | Persona cammina nel piazzale → riquadro verde `person` | ☐ | |
| 3.3 | Veicolo rilevato — Varco Carrabile | Auto entra nel varco → riquadro verde `car` | ☐ | |
| 3.4 | Veicolo rilevato — Piazzale | Auto parcheggiata → riquadro verde `car` | ☐ | |
| 3.5 | Tempo di inferenza accettabile | Debug → Performance → inference time < 100ms | ☐ | |
| 3.6 | Nessun falso positivo evidente | Nessun riquadro su muri, alberi o ombre ferme | ☐ | |

---

## Sezione 4 — Registrazione

| # | Verifica | Esito atteso | ✓ | Note |
|:-:|----------|-------------|:-:|------|
| 4.1 | Registrazione su movimento attiva | Interfaccia Frigate → Recordings → clip presenti dopo movimento | ☐ | |
| 4.2 | Nessuna registrazione a piazzale vuoto | Dopo 10 min senza movimento → nessun nuovo segmento su disco | ☐ | |
| 4.3 | Qualità registrazione 4K | Aprire una clip registrata → risoluzione 3840×2160 | ☐ | |
| 4.4 | Snapshot generato su evento | Interfaccia Frigate → Events → immagine snapshot presente | ☐ | |

---

## Sezione 5 — Lettura Targhe (LPR)

| # | Verifica | Esito atteso | ✓ | Note |
|:-:|----------|-------------|:-:|------|
| 5.1 | LPR attivo su Varco Carrabile | `config.yml` → `cameras.varco_carrabile.lpr.enabled: True` | ☐ | |
| 5.2 | Targa letta — veicolo in transito lento | Auto passa a 10–15 km/h → targa appare nell'evento LPR | ☐ | |
| 5.3 | Formato targa corretto | La targa letta rispetta il formato italiano `AA000AA` | ☐ | |
| 5.4 | Targa nota riconosciuta | Inserire una targa in `known_plates` → risultato `known` | ☐ | |

> **SE LA LETTURA TARGHE FALLISCE** (voce 5.2):
> 1. Provare con lo zoom ottico 5x della telecamera puntato sulla zona di passaggio.
> 2. Se non basta, contattare lo sviluppatore: si valuterà lo spostamento del
>    detect sul flusso 4K per questa telecamera (vedi `docs/BUDGET_RISORSE.md`,
>    Decisione Aperta 1).

| **Proprietà test LPR** | **Valore** |
|------------------------|-----------|
| Responsabile del test | Alessio |
| Responsabile della soluzione (se fallisce) | Sviluppatore |

---

## Sezione 6 — Rilevamento Audio

| # | Verifica | Esito atteso | ✓ | Note |
|:-:|----------|-------------|:-:|------|
| 6.1 | Audio attivo sulle telecamere | Microfono abilitato nelle impostazioni Reolink | ☐ | |
| 6.2 | Urlo rilevato | Riprodurre un urlo forte → evento audio `scream` o `yell` | ☐ | |
| 6.3 | Allarme incendio rilevato | Riprodurre suono allarme → evento audio `fire_alarm` | ☐ | |

> **NOTA**: Il rilevamento audio usa il microfono integrato della telecamera.
> Se non funziona, verificare nelle impostazioni Reolink che il canale audio
> sia abilitato e che il volume sia al massimo.

---

## Sezione 7 — Eventi MQTT

| # | Verifica | Esito atteso | ✓ | Note |
|:-:|----------|-------------|:-:|------|
| 7.1 | Evento pubblicato su rilevamento persona | `mosquitto_sub -h 127.0.0.1 -u USER -P PASS -t 'frigate/events'` → JSON con `type: new` | ☐ | |
| 7.2 | Review pubblicato su allarme | `mosquitto_sub -h 127.0.0.1 -u USER -P PASS -t 'frigate/reviews'` → JSON visibile | ☐ | |
| 7.3 | **Orchestratore Osservatore scrive il log** | Al passaggio di persona/auto, `tail -f storage/logs/sentinel_events.log` mostra gli eventi registrati | ☐ | |

> **COME TESTARE MQTT E L'ORCHESTRATORE dal Jetson**:
> ```bash
> # 1. Verifica diretta messaggi MQTT:
> docker exec mosquitto mosquitto_sub -h localhost -u UTENTE -P PASSWORD -t 'frigate/#' -v
>
> # 2. Verifica registro eventi orchestratore:
> tail -f storage/logs/sentinel_events.log
> ```
> Far camminare una persona davanti a una telecamera: entrambi gli output devono mostrare gli eventi.


---

## Sezione 8 — Rilevamento Telemetria Hardware (Memoria e Temperature)

> **OBIETTIVO**: Fornire i dati reali di consumo al team di sviluppo per validare
> definitivamente la sostenibilità termica e di memoria dell'Orin Nano 8GB rispetto all'Orin NX 16GB.
> Eseguire il comando `sudo tegrastats` sul Jetson per 30 secondi e ricavare i valori.

### 8.1 Misurazione al Primo Avvio a Regime (dopo 15 minuti dall'avvio con 3 flussi attivi)

| Parametro Hardware | Comando / Campo | Valore Rilevato | Valore Nominale Atteso | Note / Esito |
|--------------------|-----------------|-----------------|------------------------|--------------|
| **RAM Utilizzata** | `sudo tegrastats` → campo `RAM XXXX/7400MB` | _________ MB | < 4.500 MB | ☐ Conforme ☐ Anomalo |
| **Temperatura GPU** | `sudo tegrastats` → campo `GPU@XX.XC` | _________ °C | < 65.0 °C | ☐ Conforme ☐ Anomalo |
| **Temperatura CPU** | `sudo tegrastats` → campo `CPU@XX.XC` | _________ °C | < 65.0 °C | ☐ Conforme ☐ Anomalo |
| **Temperatura Giunzione** | `sudo tegrastats` → campo `tj@XX.XC` | _________ °C | < 70.0 °C | ☐ Conforme ☐ Anomalo |

### 8.2 Misurazione dopo 48 Ore di Funzionamento Continuo (Verifica Stabilità e Leak)

| Parametro Hardware | Comando / Campo | Valore Rilevato | Delta rispetto ad Avvio | Note / Esito |
|--------------------|-----------------|-----------------|-------------------------|--------------|
| **RAM Utilizzata** | `sudo tegrastats` → campo `RAM XXXX/7400MB` | _________ MB | _________ MB (Max +200MB) | ☐ Stabile ☐ In aumento |
| **Temperatura GPU** | `sudo tegrastats` → campo `GPU@XX.XC` | _________ °C | _________ °C | ☐ Stabile ☐ Surriscaldamento |
| **Temperatura CPU** | `sudo tegrastats` → campo `CPU@XX.XC` | _________ °C | _________ °C | ☐ Stabile ☐ Surriscaldamento |
| **Temperatura Giunzione** | `sudo tegrastats` → campo `tj@XX.XC` | _________ °C | _________ °C | ☐ Stabile ☐ Surriscaldamento |

---

## Risultato Finale

| Sezione | Esito | Firma |
|---------|-------|-------|
| 1. Infrastruttura e Sicurezza | ☐ OK  ☐ KO | |
| 2. Flussi Video | ☐ OK  ☐ KO | |
| 3. Rilevamento Oggetti | ☐ OK  ☐ KO | |
| 4. Registrazione | ☐ OK  ☐ KO | |
| 5. Lettura Targhe | ☐ OK  ☐ KO | |
| 6. Rilevamento Audio | ☐ OK  ☐ KO | |
| 7. Eventi MQTT | ☐ OK  ☐ KO | |
| 8. Telemetria Hardware (tegrastats) | ☐ Dati Inviati allo Sviluppatore | |

**Sistema collaudato il**: _______________  
**Firma tecnico (Alessio)**: _______________  
**Firma sviluppatore (se presente)**: _______________

