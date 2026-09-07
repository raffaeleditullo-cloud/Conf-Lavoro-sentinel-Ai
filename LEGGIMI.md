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
