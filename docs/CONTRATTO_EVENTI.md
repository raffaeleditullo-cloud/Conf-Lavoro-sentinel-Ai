# CONTRATTO EVENTI MQTT — Frigate 0.17.2 → Orchestratore Fase 2

Questo documento specifica i **topic MQTT e i payload JSON** pubblicati da
Frigate NVR v0.17.2 che l'orchestratore della Fase 2 dovrà consumare.

Tutti i topic usano il prefisso configurato `frigate` (valore di
`mqtt.topic_prefix` in `config.yml`). Il broker è Mosquitto in ascolto
su `127.0.0.1:1883` con autenticazione obbligatoria.

**Fonte ufficiale**: [Frigate MQTT Documentation (v0.17.2)](https://github.com/blakeblackshear/frigate/blob/v0.17.2/docs/docs/integrations/mqtt.md)

---

## 1. Topic Principali per l'Orchestratore

### 1.1 `frigate/events`

Pubblicato ad ogni cambiamento di un oggetto tracciato. I messaggi hanno
tre fasi del ciclo di vita: `new` → `update` → `end`.

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `type` | `string` | `"new"`, `"update"`, `"end"` |
| `before` | `object` | Stato precedente dell'oggetto tracciato |
| `after` | `object` | Stato corrente dell'oggetto tracciato |

#### Struttura dell'oggetto tracciato (campi `before` / `after`)

```json
{
  "id": "1607123955.475377-mxklsc",
  "camera": "varco_carrabile",
  "frame_time": 1607123961.837752,
  "snapshot": {
    "frame_time": 1607123965.975463,
    "box": [415, 489, 528, 700],
    "area": 12728,
    "region": [260, 446, 660, 846],
    "score": 0.77546,
    "attributes": []
  },
  "label": "person",
  "sub_label": null,
  "top_score": 0.958984375,
  "false_positive": false,
  "start_time": 1607123955.475377,
  "end_time": null,
  "score": 0.7890625,
  "box": [424, 500, 536, 712],
  "area": 23744,
  "ratio": 2.113207,
  "region": [264, 450, 667, 853],
  "current_zones": ["zona_accesso_veicoli"],
  "entered_zones": ["zona_accesso_veicoli"],
  "thumbnail": null,
  "has_snapshot": true,
  "has_clip": false,
  "active": true,
  "stationary": false,
  "motionless_count": 0,
  "position_changes": 2,
  "attributes": {},
  "current_attributes": [],
  "current_estimated_speed": null,
  "average_estimated_speed": null,
  "velocity_angle": null,
  "recognized_license_plate": "AB123CD",
  "recognized_license_plate_score": 0.933451
}
```

#### Campi rilevanti per l'orchestratore

| Campo | Uso nell'orchestratore |
|-------|------------------------|
| `id` | Identificativo univoco dell'evento (chiave primaria) |
| `camera` | Nome telecamera: `varco_carrabile`, `varco_pedonale`, `piazzale` |
| `label` | Tipo oggetto: `person`, `car`, `motorcycle`, `bicycle`, `bus`, `truck` |
| `type` (envelope) | `new` = inizio tracciamento, `end` = uscita dall'inquadratura |
| `current_zones` | Zone attive in questo frame (nomi definiti in `config.yml`) |
| `entered_zones` | Tutte le zone attraversate durante il tracciamento |
| `top_score` | Confidenza massima raggiunta durante il tracciamento |
| `start_time` / `end_time` | Timestamp UNIX per durata della permanenza |
| `stationary` | `true` se l'oggetto è fermo (utile per veicoli parcheggiati) |
| `recognized_license_plate` | Targa letta (solo su `varco_carrabile` con LPR attivo) |
| `recognized_license_plate_score` | Confidenza della lettura targa |
| `has_snapshot` | Se è disponibile uno snapshot tramite API HTTP |

#### Logica di consumo consigliata

1. **Sottoscriversi a** `frigate/events`
2. **Filtrare per** `type == "new"` per nuovi ingressi e `type == "end"` per uscite
3. **Ignorare** `type == "update"` a meno che non servano aggiornamenti in tempo reale della posizione
4. **Verificare** `false_positive == false` (Frigate può marcare l'evento come falso positivo)
5. **Per allarmi**: controllare `label` e `current_zones` per decidere l'escalation
6. **Per LPR**: usare `recognized_license_plate` quando presente e `recognized_license_plate_score > 0.90`

---

### 1.2 `frigate/reviews`

Pubblicato per ciascun evento di review (raggruppamento di rilevamenti).
I review hanno severità `detection` o `alert` in base alla configurazione
`review.alerts.labels` e `review.detections.labels` nel `config.yml`.

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `type` | `string` | `"new"`, `"update"`, `"end"` |
| `before` | `object` | Stato precedente del review |
| `after` | `object` | Stato corrente del review |

#### Struttura del review

```json
{
  "id": "1718987129.308396-fqk5ka",
  "camera": "varco_pedonale",
  "start_time": 1718987129.308396,
  "end_time": null,
  "severity": "alert",
  "thumb_path": "/media/frigate/clips/review/thumb-varco_pedonale-1718987129.308396-fqk5ka.webp",
  "data": {
    "detections": [
      "1718987128.947436-g92ztx",
      "1718987148.879516-d7oq7r"
    ],
    "objects": ["person", "car"],
    "sub_labels": [],
    "zones": ["zona_transito_pedoni"],
    "audio": []
  }
}
```

#### Mappatura severità → azione nell'orchestratore

| Severità | Label che la generano (da `config.yml`) | Azione suggerita |
|----------|----------------------------------------|------------------|
| `alert` | `person`, `car` | Notifica immediata, attivazione relè/speaker |
| `detection` | `motorcycle`, `bicycle`, `bus`, `truck` | Registrazione per audit, nessun allarme sonoro |

---

### 1.3 `frigate/tracked_object_update`

Aggiornamenti ai metadati degli oggetti tracciati. L'orchestratore deve
sottoscriversi a questo topic per ricevere i risultati della lettura targhe
in tempo reale.

#### Aggiornamento LPR (Lettura Targa)

```json
{
  "type": "lpr",
  "id": "1607123955.475377-mxklsc",
  "name": "Furgone Magazzino 1",
  "plate": "AB123CD",
  "score": 0.95,
  "camera": "varco_carrabile",
  "timestamp": 1607123958.748393
}
```

| Campo | Descrizione |
|-------|-------------|
| `type` | Sempre `"lpr"` per gli aggiornamenti targa |
| `id` | ID dell'evento (corrisponde a `frigate/events`) |
| `name` | Nome associato alla targa in `known_plates`, o `null` se sconosciuta |
| `plate` | Testo della targa letta |
| `score` | Confidenza della lettura |
| `camera` | Sempre `"varco_carrabile"` (unica camera con LPR attivo) |
| `timestamp` | Timestamp UNIX della lettura |

#### Logica LPR per l'orchestratore

1. Ricevere il messaggio `type == "lpr"` da `frigate/tracked_object_update`
2. Se `name != null` → targa nota → azione automatica (es. apertura sbarra)
3. Se `name == null` e `score >= 0.90` → targa sconosciuta → segnalare
4. Se `score < 0.90` → lettura incerta → ignorare o richiedere verifica manuale

---

## 2. Topic di Stato per Telecamere

### 2.1 `frigate/<camera_name>/status/<role>`

| Topic | Valori | Uso |
|-------|--------|-----|
| `frigate/varco_carrabile/status/detect` | `online`, `offline`, `disabled` | Monitoraggio salute |
| `frigate/varco_carrabile/status/record` | `online`, `offline`, `disabled` | Monitoraggio salute |
| `frigate/varco_carrabile/status/audio` | `online`, `offline`, `disabled` | Monitoraggio salute |

Stesso schema per `varco_pedonale` e `piazzale`.

### 2.2 `frigate/<camera_name>/<object_name>`

Conteggio oggetti per telecamera (intero). Esempio:
- `frigate/piazzale/person` → `2`
- `frigate/varco_carrabile/car` → `1`

### 2.3 `frigate/<camera_name>/audio/<audio_type>`

| Topic | Valori | Uso |
|-------|--------|-----|
| `frigate/varco_carrabile/audio/scream` | `ON`, `OFF` | Allarme urla |
| `frigate/varco_pedonale/audio/yell` | `ON`, `OFF` | Allarme urla |
| `frigate/piazzale/audio/fire_alarm` | `ON`, `OFF` | Allarme incendio |

### 2.4 `frigate/<camera_name>/motion`

Stato rilevamento movimento. Valori: `ON`, `OFF`.
Il valore resta `ON` per 30 secondi dopo l'ultimo movimento rilevato.

### 2.5 `frigate/<camera_name>/review_status`

Stato attività corrente della telecamera. Valori: `NONE`, `DETECTION`, `ALERT`.

---

## 3. Topic di Controllo (Comandi dall'Orchestratore a Frigate)

L'orchestratore può controllare Frigate pubblicando su questi topic:

| Topic | Valori | Effetto |
|-------|--------|---------|
| `frigate/<camera>/detect/set` | `ON` / `OFF` | Abilita/disabilita rilevamento |
| `frigate/<camera>/recordings/set` | `ON` / `OFF` | Abilita/disabilita registrazione |
| `frigate/<camera>/audio/set` | `ON` / `OFF` | Abilita/disabilita audio |
| `frigate/<camera>/snapshots/set` | `ON` / `OFF` | Abilita/disabilita snapshot |
| `frigate/<camera>/enabled/set` | `ON` / `OFF` | Abilita/disabilita intera camera |
| `frigate/notifications/set` | `ON` / `OFF` | Abilita/disabilita notifiche globali |

---

## 4. Topic di Sistema

| Topic | Tipo | Descrizione |
|-------|------|-------------|
| `frigate/available` | `string` | `"online"` all'avvio, `"offline"` allo stop |
| `frigate/stats` | `JSON` | Statistiche sistema (CPU, GPU, FPS, latenza inferenza) |
| `frigate/camera_activity` | `JSON` | Stato corrente features per ogni camera |

---

## 5. Nomi Telecamere e Zone (Valori Effettivi)

Questi sono i valori esatti che appariranno nei campi `camera` e `current_zones`
dei messaggi MQTT. Corrispondono ai nomi definiti in `config/config.yml`.

### Telecamere

| Nome MQTT | Descrizione |
|-----------|-------------|
| `varco_carrabile` | Ingresso veicoli (con LPR attivo) |
| `varco_pedonale` | Ingresso pedonale (face_recognition predisposto, spento) |
| `piazzale` | Area parcheggio e perimetro |

### Zone

| Nome MQTT | Telecamera | Oggetti tracciati |
|-----------|------------|-------------------|
| `zona_accesso_veicoli` | `varco_carrabile` | car, motorcycle, bus, truck |
| `zona_transito_pedoni` | `varco_pedonale` | person |
| `zona_parcheggio` | `piazzale` | car, truck |
| `zona_perimetro` | `piazzale` | person |

### Etichette Oggetti

| Label MQTT | Descrizione | Severity in review |
|-----------|-------------|-------------------|
| `person` | Persona | `alert` |
| `car` | Automobile | `alert` |
| `motorcycle` | Motociclo | `detection` |
| `bicycle` | Bicicletta | `detection` |
| `bus` | Autobus | `detection` |
| `truck` | Camion/furgone | `detection` |

### Tipi Audio

| Label MQTT | Descrizione |
|-----------|-------------|
| `scream` | Urlo |
| `yell` | Grido |
| `fire_alarm` | Allarme antincendio |

---

## 6. Formato Registro Diagnostico per la Fase 2 (JSON Lines)

Il demone `orchestrator` scrive tutti i messaggi ricevuti dal broker nel file:
`storage/logs/sentinel_events.log`

Il file adotta il formato **JSON Lines (JSONL)**: ogni riga è un oggetto JSON
autonomo e valido, privo di a capo interni, direttamente deserializzabile
da script di test o riproducibile tramite mock MQTT nella Fase 2.

### Schema del Record JSONL

```json
{
  "timestamp": "2026-09-07T12:00:05.123456+02:00",
  "topic": "frigate/events",
  "payload_bytes": 1420,
  "type": "json",
  "payload": {
    "type": "new",
    "before": {...},
    "after": {...}
  }
}
```

### Definizione Campi

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `timestamp` | `string` | Data e ora di ricezione in standard ISO 8601 con fuso orario esplicito (es. `+02:00`). |
| `topic` | `string` | Nome completo del topic MQTT (es. `frigate/events`, `frigate/stats`, `frigate/varco_carrabile/car`). |
| `payload_bytes` | `integer` | Dimensione originaria del payload grezzo in byte. |
| `type` | `string` | Tipologia del messaggio registrato: `"json"`, `"text"`, `"binary"`, `"truncated"`. |
| `payload` | `object` / `string` | **Contenuto del messaggio**: se JSON valido, è annidato come dizionario/lista nativa; se testo normale, è una stringa; se `"binary"` (es. frame snapshot JPEG), il campo è omesso. |
| `original_length` | `integer` | *(Opzionale)* Presente solo se `type == "truncated"` (testi superiori a 3.000 caratteri). |

