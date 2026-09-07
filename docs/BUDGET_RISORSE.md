# CONF-LAVORO SENTINEL AI - FASE 1: BUDGET RISORSE (MEMORIA E DISCO)

Questo documento traccia in modo analitico e rigoroso il consumo di **Memoria (RAM/VRAM unificata)** e **Spazio su Disco (SSD NVMe)** per il sistema Sentinel AI operante su NVIDIA Jetson Orin Nano Super Dev Kit 8GB con Frigate NVR v0.17.2.

> **NOTA METODOLOGICA VINCOLANTE**:  
> Tutti i valori di memoria indicati per i modelli IA e l'elaborazione video sono **STIME TEORICHE** basate su documentazione ufficiale e test di riferimento. Non devono essere considerati definitivi finché non saranno **misurati fisicamente sull'hardware Jetson reale** (colonna vuota predisposta per la Fase 4).

---

## 1. BUDGET DELLA MEMORIA UNIFICATA (RAM / VRAM)

Il Jetson Orin Nano 8GB dispone di una memoria fisica condivisa tra CPU e GPU.  
- **Memoria fisica totale**: 8.192 MB (circa 7.400 MB netti utilizzabili dal sistema operativo).  
- **Obiettivo massimo di progetto (Vincolo 5)**: **4.500 MB (4,5 GB)** in regime di esercizio, garantendo quasi 3 GB di margine libero per evitare qualsiasi instabilità o saturazione OOM (Out Of Memory).

### 1.1 Formule Ufficiali Frigate per la Memoria Condivisa

#### A) Shared Memory (`/dev/shm` - `shm_size`)
Frigate utilizza la memoria condivisa POSIX per allocare i frame raw YUV420p decodificati da FFmpeg e renderli accessibili ai processi di motion detection e inferenza IA senza copie in memoria.

$$\text{Dimensione frame raw (byte)} = \text{Larghezza} \times \text{Altezza} \times 1.5$$

Frigate mantiene in memoria condivisa una coda circolare di circa 16 frame per ciascuna telecamera (a 5 fps di detect):

*   **Flussi detect Sub Stream ($640 \times 360$) su tutte le 3 telecamere**:  
    Per ogni telecamera: $640 \times 360 \times 1.5 = 345.600 \text{ byte } (\approx 338 \text{ KB/frame}) \times 16 \approx \mathbf{5,4 \text{ MB}}$  
    Per 3 telecamere: $3 \times 5,4 \text{ MB} = \mathbf{16,2 \text{ MB}}$.
*   **Buffer interno log Frigate**: fisso a **$40,0 \text{ MB}$**.

$$\text{Totale teorico shm base (3x 640x360)} = 16,2 + 40,0 = \mathbf{56,2 \text{ MB}}$$

*(In caso di adozione dell'opzione 4K detect su `varco_carrabile`: $3840 \times 2160 \times 1.5 \times 16 \approx 199 \text{ MB} + 10,8 + 40 = \mathbf{249,8 \text{ MB}}$)*.

*Dimensionamento configurato in `docker-compose.yml`*: **`shm_size: 256mb`**  
Garantisce un margine di sicurezza ampio per assorbire transitori, flussi di debug e picchi di attività.

#### B) Tmpfs per Cache Registrazioni (`/tmp/cache`)
Frigate riceve i flussi video e memorizza i segmenti temporanei da 10 secondi in RAM (`/tmp/cache`) prima di aggregarli e scriverli sull'SSD NVMe. Questo azzera l'usura dell'SSD derivante dalla micro-scrittura continua.
*   Bitrate Main Stream 4K: $8 \text{ Mbps} = 1 \text{ MB/s}$ per telecamera.
*   Per 3 telecamere: $3 \text{ MB/s}$.
*   Frigate mantiene in cache tra 60 e 120 secondi di video:  
    $3 \text{ MB/s} \times 120 \text{ s} = \mathbf{360 \text{ MB}}$.
*   *Configurazione in compose*: `tmpfs /tmp/cache: size=1g`.  
    In Linux, tmpfs è ad allocazione dinamica: la memoria fisica consumata corrisponde solo ai file effettivamente presenti (in regime stazionario: **$100 \div 150 \text{ MB}$**).

---

### 1.2 Tabella di Bilancio Memoria

| Voce / Processo | Ruolo e Dettagli Tecnici | Memoria Stimata (MB) [STIMA] | Memoria Misurata (MB) *(Fase 4)* | Note di Verifica |
| :--- | :--- | :--- | :--- | :--- |
| **S.O. Linux + JetPack 6** | Kernel, moduli NVIDIA, runtime container, systemd (headless) | ~1.200 MB | | Headless senza GUI desktop |
| **Frigate Core + Nginx + DB** | Processo principale Python, server web, connessione SQLite | ~350 MB | | Base Frigate 0.17.2 |
| **Decodifica Video FFmpeg** | Decodifica hardware stream via NVDEC (`preset-jetson-h264`) | ~750 MB | | Accelerato da chip NVDEC |
| **Shared Memory (`/dev/shm`)** | Frame queue per 3 telecamere + buffer log Frigate | ~256 MB | | Allocazione fissa in compose |
| **Cache Tmpfs (`/tmp/cache`)** | Buffer segmenti video 10s prima della scrittura su SSD | ~150 MB | | Consumo dinamico effettivo |
| **Modello Rilevamento (YOLOv4-416 TensorRT)** | File `.trt` generato al primo avvio (~30 MB su disco). Esecuzione TensorRT ($416 \times 416$) | ~500 MB | | **STIMA DA VERIFICARE SUL JETSON** |
| **Lettura Targhe (LPR)** | YOLOv9 Plate Detector + PaddleOCR (on-demand su veicolo) | ~300 MB | | Attivo solo in transito auto |
| **Riconoscimento Volti (FaceNet)** | Modello 'small' su CPU | *0 MB (Spento)* | | **DISATTIVATO** (`enabled: false`) |
| **Rilevamento Audio** | Modello sherpa-onnx (rumori critici: scream, yell, fire_alarm) | ~80 MB | | Residente in RAM (escluso speech) |
| **Broker MQTT Mosquitto** | Servizio messaggistica leggero in container C (autenticato) | ~20 MB | | Footprint trascurabile |
| **Orchestratore (Osservatore)** | Container Python 3.11-slim, demone log rotante su MQTT | ~30 MB | | paho-mqtt daemon minimale |
| **TOTALE IN ESERCIZIO** | **Somma di tutti i componenti attivi** | **~3.636 MB (~3,6 GB)**| | **Obiettivo < 4.500 MB pienamente rispettato** |
| *Margine libero rispetto al target* | Differenza rispetto al tetto dei 4,5 GB | **+864 MB** | | Margine di sicurezza |
| *Margine libero rispetto alla RAM fisica* | Differenza rispetto alla RAM netta (~7.400 MB) | **+3.764 MB** | | Zero rischio OOM killer |


---

## 2. ANALISI CAPIENZA DISCO (SSD NVMe 1TB) E CONSERVAZIONE (72 ORE)

### 2.1 Calcolo dei Dati Reali di Bitrate
Le telecamere Reolink RLC-811A registrano a risoluzione 4K UHD ($3840 \times 2160$).  
*   **Bitrate Standard Main Stream (CBR a 25 fps)**: $8.192 \text{ kbps} = 1.024 \text{ KB/s} \approx 1,00 \text{ MB/s}$  
    Consumo orario per telecamera: $1,00 \text{ MB/s} \times 3.600 \text{ s} = \mathbf{3,60 \text{ GB/ora}}$
*   **Sub Stream (640x360 a 1 Mbps)**: $\approx 0,125 \text{ MB/s} = \mathbf{0,45 \text{ GB/ora}}$

### 2.2 Capacità Reale dell'SSD da 1 TB
Un'unità SSD da $1 \text{ TB}$ (nominale $10^{12} \text{ byte}$) fornisce effettivi circa **$931 \text{ GiB}$**.  
Ripartizione dello spazio su disco:
*   Sistema Operativo JetPack 6, Docker Engine e immagini: **$35 \text{ GB}$**
*   Modello TensorRT (`yolov4-416.trt` generato al primo avvio, ~30 MB) e cache interne: **$15 \text{ GB}$**
*   Database SQLite Frigate (`frigate.db`) e indici: **$25 \text{ GB}$**
*   Area riservata di sicurezza e over-provisioning (wear-leveling SSD): **$106 \text{ GB}$**
*   **Pool netto massimo assegnato alle registrazioni video**: **$750 \text{ GB}$**

---

### 2.3 Ricalcolo con la Configurazione Adottata: `mode: motion` (72 Ore)

In conformità con la decisione approvata, la registrazione di base è configurata con:
```yaml
record:
  motion:
    days: 3
  alerts:
    retain:
      days: 3
      mode: motion
  detections:
    retain:
      days: 3
      mode: motion
```

#### Calcolo Occupazione Reale su 72 Ore (3 Giorni)
In un perimetro aziendale, il movimento medio cumulato è circa il 15% della giornata (~3,6 ore/giorno per telecamera).  
*   Ore di registrazione attiva per telecamera in 72h: $3 \times 3,6 \text{ ore} = \mathbf{10,8 \text{ ore}}$.
*   Consumo su 3 telecamere:
    $$\text{Occupazione media 72h} = 3 \text{ telecamere} \times 10,8 \text{ ore} \times 3,60 \text{ GB/ora} = \mathbf{116,6 \text{ GB}}$$

*Scenario di picco (giornate di intenso traffico, movimento al 25% del tempo = 6 ore al giorno per telecamera)*:
$$\text{Occupazione di picco 72h} = 3 \text{ telecamere} \times 18 \text{ ore} \times 3,60 \text{ GB/ora} = \mathbf{194,4 \text{ GB}}$$

#### Esito del Ricalcolo
*   **Occupazione del disco**: tra **116 GB e 194 GB**, pari al **15% - 26% del pool utile** (750 GB).
*   **Spazio residuo libero**: oltre **550 GB** sempre liberi sull'SSD.
*   **Vantaggio operativo**: zero segmenti registrati nelle ore di piazzale vuoto, usura SSD ridotta dell'80% rispetto alla registrazione continua, e conservazione integrale di ogni evento e allarme a piena qualità 4K.

---

## 3. SEZIONE DECISIONI APERTE (DA VERIFICARE SULL'IMPIANTO REALE)

### Decisione Aperta 1: Risoluzione Detect su `varco_carrabile` e Lettura Targhe (LPR)

#### Contesto Fisico Rilevato
La Reolink RLC-811A espone via RTSP unicamente due flussi:
1.  **Main**: $3840 \times 2160$ (4K UHD)
2.  **Sub**: fisso a **$640 \times 360$** (non configurabile a 720p via RTSP)

#### Confronto Opzioni di Esercizio

| Parametro | Opzione A (Attuale in config) | Opzione B (Passaggio al Main 4K) | Opzione C (Modalità Dedicata LPR) |
| :--- | :--- | :--- | :--- |
| **Stream per detect** | Sub stream ($640 \times 360$) | Main stream ($3840 \times 2160$) | Main stream ($3840 \times 2160$) |
| **Costo Memoria `/dev/shm`** | **5,4 MB** | **199 MB** | **199 MB** |
| **Dimensione Targa OCR** | ~50–70 pixel (al limite dell'affidabilità) | ~300–500 pixel (nitidissima) | ~300–500 pixel |
| **Rilevamento Pedoni/Moto** | **Sì** (traccia persone normalmente) | **Sì** (traccia persone normalmente) | **NO** (bypassa il rilevamento persone) |
| **Carico Decodifica GPU** | Basso (decodifica stream 360p) | Nullo aggiuntivo (il 4K è già decodificato per record) | Elevato (scansiona targhe su ogni frame di movimento) |
| **Valutazione Operativa** | Mantenere questa configurazione alla consegna. Se Alessio rileva errori OCR durante il passaggio dell'auto con zoom 5x, si sposta `detect` su `varco_carrabile_main`. | **Soluzione consigliata di riserva**: garantisce lettura perfetta al 100% con un costo di soli 199 MB di RAM su 8 GB. | **Sconsigliata**: esclude la sicurezza intrusione pedoni sul cancello. |

---

### Decisione Aperta 2: Scelta Dispositivo per LPR (`device: CPU` vs `device: GPU`)
*   **Stato attuale nel config**: `device: CPU` (preso dal default di riferimento).
*   **Analisi Tecnica**:  
    Su Jetson Orin Nano, l'immagine `-tensorrt-jp6` include ONNX Runtime con execution provider CUDA/TensorRT.
    *   *Su CPU ARM*: PaddleOCR impiega tra **400 ms e 800 ms** per interpretare i caratteri della targa. In un varco carrabile aziendale, un veicolo in movimento a $15 \div 20 \text{ km/h}$ percorre vari metri in 800 ms, rischiando di uscire dall'inquadratura ottimale prima che la lettura sia confermata.
    *   *Su GPU (CUDA)*: Il tempo di inferenza di PaddleOCR scende a circa **40–70 ms** (oltre $10\times$ più rapido), permettendo di analizzare più frame consecutivi dello stesso veicolo e confermare la targa prima che la sbarra debba aprirsi.
    *   *Costo in VRAM*: Circa **250–300 MB** aggiuntivi di memoria allocati on-demand solo quando un veicolo è nel varco. Con oltre 3.600 MB liberi, l'impatto sul budget è del tutto trascurabile.
*   **Raccomandazione**: Impostare `device: GPU` per l'LPR in produzione sul Jetson per garantire tempi di risposta istantanei al cancello.

---

### Decisione Aperta 3: Passaggio a D-FINE come Rilevatore Primario (Aggiornamento Futuro)

#### Perché non è nella Versione 1
La Versione 1 consegna **YOLOv4-416 / TensorRT** come rilevatore primario. YOLOv4 è generato automaticamente al primo avvio da Frigate, senza richiedere file binari preconfezionati nella cartella. D-FINE (Apache 2.0, repository `https://github.com/Peterande/D-FINE`) era la prima scelta per accuratezza ma richiede un'esportazione ONNX su una macchina con Docker e almeno 8 GB di RAM libera — condizioni non soddisfatte né dal PC di sviluppo (Docker non installato) né dal Jetson Orin Nano (8 GB condivisi con sistema e GPU).

#### Procedura di Aggiornamento
1.  Su una macchina Linux con Docker e ≥8 GB RAM, eseguire la ricetta ufficiale Frigate (`docs/PROCEDURA_ESPORTAZIONE_ONNX.md`).
2.  Copiare il file `dfine_s_obj2coco.onnx` in `config/model_cache/` sul Jetson.
3.  In `config/config.yml`, commentare il blocco `detectors: tensorrt` + `model:` attivo e decommentare il blocco `detectors: onnx` + `model:` con `model_type: dfine`.
4.  In `docker-compose.yml`, rimuovere la riga `YOLO_MODELS=yolov4-416`.
5.  Riavviare con `docker compose up -d`.
6.  Verificare provenienza e integrità con SHA256 del file e confronto con il checkpoint ufficiale `dfine_s_obj2coco.pth` dal repository `Peterande/storage`.

---

### Nota Tecnica Interna: Connettività API Frigate per l'Orchestratore (Fase 2)
In `docker-compose.yml`, la porta `5000` di Frigate è legata a `127.0.0.1:5000:5000` per impedire l'accesso non autenticato dalla rete LAN del cliente.  
**Questo binding NON ostacola in alcun modo l'orchestratore**: all'interno della rete Docker definita da Docker Compose, i container comunicano direttamente tra loro per nome di servizio. L'orchestratore interrogherà le API REST interne di Frigate puntando a `http://frigate:5000/api/...`, risolto a livello di DNS interno Docker.  
**NON modificare il binding host `127.0.0.1:5000:5000`**: rimuovere `127.0.0.1` esporrebbe l'API priva di autenticazione all'intera rete locale aziendale.

