# CONF-LAVORO SENTINEL AI — Fase 1: Motore Percettivo

Sistema di videosorveglianza IA basato su **Frigate NVR v0.17.2** (licenza MIT).

---

## Che cos'è questa cartella

Contiene tutto il necessario per avviare il sistema di videosorveglianza IA
sul **Jetson Orin Nano Super Dev Kit 8GB** del cliente. Il sistema gestisce
3 telecamere Reolink RLC-811A 4K e fornisce:

- Rilevamento oggetti in tempo reale (persone, veicoli) via TensorRT
- Registrazione video su movimento a qualità 4K
- Lettura targhe automatica (LPR) sul varco carrabile
- Rilevamento audio di emergenza (urla, allarme incendio)
- Pubblicazione eventi MQTT per l'orchestratore (Fase 2)

> **PRECISAZIONE IMPORTANTE SULL'INTERFACCIA WEB**  
> L'interfaccia web accessibile sulla porta `8971` è quella tecnica interna del motore
> percettivo (Frigate NVR), utile esclusivamente per il collaudo hardware e lo streaming di verifica.
> **NON è l'interfaccia finale del prodotto commerciale.** La piattaforma utente con marchio
> e cruscotto CONF-LAVORO Sentinel AI sarà fornita con l'orchestratore nella Fase 2.

---

## Cosa fare — 5 passi

| Passo | Cosa | Documento di riferimento |
|:-----:|------|--------------------------|
| **0** | Copiare la cartella sul Jetson nel percorso di lavoro (`/home/sentinel/sentinel-ai`) | [`docs/MANUALE_ALESSIO.md` → Passo 0](docs/MANUALE_ALESSIO.md) |
| **1** | Verificare i prerequisiti e generare la password MQTT | [`docs/MANUALE_ALESSIO.md` → Passo 1](docs/MANUALE_ALESSIO.md) |
| **2** | Compilare il file `.env` con gli indirizzi IP e le credenziali | [`docs/MANUALE_ALESSIO.md` → Passo 2](docs/MANUALE_ALESSIO.md) |
| **3** | Avviare il sistema con `docker compose up -d` e recuperare la password admin iniziale | [`docs/MANUALE_ALESSIO.md` → Passo 4](docs/MANUALE_ALESSIO.md) |
| **4** | Eseguire la checklist di collaudo e misurare memoria/temperatura | [`docs/CHECKLIST_COLLAUDO.md`](docs/CHECKLIST_COLLAUDO.md) |

> **ATTENZIONE — PRIMO AVVIO**  
> Al primo avvio il sistema genera il modello IA TensorRT per il rilevamento oggetti.
> Il processo richiede **3–5 minuti** durante i quali il container sembra fermo
> e le telecamere non mostrano rilevamenti. **NON riavviare il container.**  
> Il modello è pronto quando le righe relative alla conversione nei log si interrompono
> e riprende l'elaborazione ordinaria dei flussi video (`docker compose logs -f frigate`).


---

## Altoparlante Fanvil A233 — Dissuasione vocale (Multicast RTP)

La riproduzione degli avvisi vocali **non usa chiamate HTTP/CGI né SIP**: il sistema
invia l'audio come flusso **Multicast RTP** con `ffmpeg`, sul canale che l'A233
ascolta già di suo.

| Parametro | Valore predefinito | Variabile d'ambiente |
|-----------|--------------------|----------------------|
| Indirizzo multicast | `239.255.1.1` | `FANVIL_MULTICAST_IP` |
| Porta | `5004` | `FANVIL_MULTICAST_PORT` |
| Codec | G.711 µ-law, 8 kHz, mono | *(fisso)* |
| Volume | cursore della dashboard (`voice_volume`) | `FANVIL_DEFAULT_VOLUME` (ripiego, 0-100) |

> **CONFIGURAZIONE OBBLIGATORIA SULLO SPEAKER (nota di Alessio)**
> Nell'interfaccia web del Fanvil A233 vanno **disattivati** i due toni di servizio:
> - **Multicast Tone**
> - **Auto HangUp Tone**
>
> Se restano attivi, al termine di ogni annuncio lo speaker emette **3 bip**
> che si sovrappongono all'avviso di dissuasione.

> **PERCHÉ I CONTAINER USANO LA RETE DELL'HOST**
> I servizi `orchestrator` e `dashboard` girano con `network_mode: host` in
> `docker-compose.yml`: con la rete bridge di Docker i pacchetti multicast
> restano confinati in `docker0` e non raggiungono mai l'altoparlante.
> Di conseguenza i nomi dei container non sono risolvibili: il codice ripiega
> automaticamente su `127.0.0.1` per il broker MQTT (`mosquitto`) e per l'API
> interna di Frigate, entrambi già pubblicati su loopback. Nessuna modifica
> al file `.env` è necessaria.

> **VERIFICA RAPIDA IN CAMPO**
> Dall'host, con lo speaker alimentato e in rete:
> ```
> ffmpeg -re -i orchestrator/audio/carmelo/03_avviso_dissuasione.mp3 \
>        -af volume=0.85 -ac 1 -ar 8000 -acodec pcm_mulaw \
>        -payload_type 0 -f rtp rtp://239.255.1.1:5004
> ```
> Se si sente l'annuncio, il canale è corretto e il problema è eventualmente
> nel container (manca `ffmpeg` nell'immagine o non è attiva la rete host).

### AudioBus e Riflesso L0 (voce immediata)

Gli annunci non avviano più un processo `ffmpeg` ciascuno: un solo componente,
l'**AudioBus** (`orchestrator/rtp_audio_bus.py`), trasmette direttamente i pacchetti
RTP verso lo speaker con lo stesso formato del comando qui sopra, e decide le
priorità (manomissione > allarmi > riflesso > frase di ORIN). Le tracce MP3 vengono
convertite una sola volta all'avvio e restano in memoria.

Al primo rilevamento a sistema armato parte il **Riflesso** (`reflex_engine.py`):
una frase breve già pronta (es. *"Rilevata presenza. Identificazione in corso."*),
seguita senza pause dalla frase contestuale di ORIN.

| Cosa | Come |
|------|------|
| Generare la libreria delle frasi | `python scripts/generate_reflex_library.py` (prima `--check` per verificare il formato) |
| Senza libreria | il Riflesso usa le tracce `03_avviso_dissuasione` / `04_allarme_intrusione` |
| Disattivare il Riflesso | `REFLEX_ENABLED=false` nel `.env` |
| Leggere la latenza nei log | righe `[RIFLESSO L0]` e `AudioBus: IN ONDA ... a N ms dalla richiesta` |
| Prima parola tagliata | aumentare `FANVIL_RTP_DELAY_MS` (pre-roll di silenzio) |

---

## Dashboard ORIN (porta 8080)

La dashboard ha un nuovo aspetto: al centro l'occhio di ORIN, in basso una barra in cui si
scrive cosa si vuole vedere, e le pagine di sempre (telecamere, eventi, targhe, stato della
Jetson, impostazioni) che si aprono come finestre. Il funzionamento sotto è lo stesso di prima.

| Cosa | Come |
|------|------|
| Aggiornare | `git pull`, poi `docker compose restart dashboard` e nel browser **Ctrl+F5** |
| Comandi di esempio | `piazzale`, `telecamera 2`, `tutte le telecamere`, `eventi`, `targhe`, `impostazioni`, `stato jetson`, `accendi i fari`, `chiudi tutto`, `aiuto` |
| Finestre | si trascinano dalla barra del titolo, doppio clic per ingrandire, **Esc** chiude |
| Scorciatoia | il tasto **/** porta alla barra dei comandi |
| Aggiungere un sinonimo | blocco `VOCABOLARIO` in `dashboard/assets/orin-commands.js`, poi `node dashboard/test/orin-commands.test.js` |
| Tornare all'aspetto precedente | `git revert` del commit ORIN: il resto del sistema non cambia |

---

## Struttura della cartella

```
.
├── LEGGIMI.md                        ← Questo file
├── docker-compose.yml                ← Definizione dei servizi Docker
├── .env.example                      ← Modello delle variabili d'ambiente
├── .env                              ← Variabili d'ambiente (DA COMPILARE)
├── config/
│   ├── config.yml                    ← Configurazione principale Frigate
│   └── model_cache/                  ← Cache modelli (generata al primo avvio)
├── mosquitto/
│   └── config/
│       ├── mosquitto.conf            ← Configurazione broker MQTT
│       └── pwfile                    ← File password MQTT (DA GENERARE)
├── orchestrator/
│   ├── Dockerfile                    ← Build container orchestratore osservatore
│   ├── observer.py                   ← Daemon Python di registrazione eventi MQTT
│   └── requirements.txt              ← Dipendenza paho-mqtt
├── docs/
│   ├── MANUALE_ALESSIO.md            ← Procedura operativa completa
│   ├── CHECKLIST_COLLAUDO.md         ← Checklist di verifica in campo
│   ├── CONTRATTO_EVENTI.md           ← Specifica MQTT per l'orchestratore
│   ├── BUDGET_RISORSE.md             ← Analisi risorse e dimensionamento
│   └── PROCEDURA_ESPORTAZIONE_ONNX.md ← Esportazione modello D-FINE (futuro)
└── storage/
    ├── recordings/                   ← Registrazioni video 4K
    ├── db/                           ← Database SQLite Frigate
    └── logs/                         ← Registro eventi MQTT (sentinel_events.log)

```

---

## Contatti in caso di problemi

| Tipo di problema | Chi chiamare |
|------------------|--------------|
| Cavo, rete, alimentazione, montaggio telecamere | Alessio (tecnico hardware) |
| Configurazione Frigate, errori IA, MQTT | Sviluppatore (noi) |

La tabella completa dei problemi e delle competenze è in
[`docs/MANUALE_ALESSIO.md` → Risoluzione Problemi](docs/MANUALE_ALESSIO.md).
