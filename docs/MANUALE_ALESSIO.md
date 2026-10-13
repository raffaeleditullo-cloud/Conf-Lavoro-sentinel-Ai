# MANUALE OPERATIVO — Installazione Sentinel AI su Jetson Orin Nano

Documento destinato ad **Alessio** (tecnico hardware). Contiene tutti i passi
necessari per portare il sistema da "cartella su chiavetta" a "funzionante
sul Jetson con 3 telecamere attive".

> **PRECISAZIONE SULL'INTERFACCIA WEB**  
> L'interfaccia web a cui accederai sulla porta `8971` (HTTPS) è la dashboard tecnica
> del motore percettivo (Frigate NVR). Serve unicamente a noi e a te per collaudare
> flussi video, inquadrature e bounding box. **NON è l'interfaccia grafica del prodotto
> commerciale**: l'applicazione completa brandizzata CONF-LAVORO Sentinel AI sarà
> integrata tramite l'orchestratore nella Fase 2.

---

## Passo 0 — Posizionamento della cartella sul Jetson

Prima di eseguire qualsiasi comando, posizionare la cartella di lavoro sul Jetson:

1. **Percorso di lavoro consigliato**: `/home/sentinel/sentinel-ai`  
   (se l'utente sul Jetson ha un nome diverso, es. `jetson`, usare `/home/jetson/sentinel-ai`).

2. **Copia da chiavetta USB**:
   ```bash
   # Individuare il punto di mount della chiavetta (es. /media/sentinel/USB_DRIVE)
   # Copiare l'intera cartella nel percorso di destinazione:
   cp -r "/media/$USER/USB_DRIVE/Conf_lavoro Sentinel AI" /home/$USER/sentinel-ai

   # Entrare nella cartella di lavoro:
   cd /home/$USER/sentinel-ai
   ```

3. **Verificare di essere nella cartella corretta**:
   ```bash
   pwd
   # Deve restituire: /home/<utente>/sentinel-ai
   ls -la
   # Devono essere visibili: docker-compose.yml, LEGGIMI.md, .env.example, config/, docs/, mosquitto/
   ```

---

## Prerequisiti

Prima di procedere con i passi successivi, verificare che sul Jetson siano soddisfatti i requisiti:

| Requisito | Come verificare | Valore atteso |
|-----------|-----------------|---------------|
| **JetPack 6 installato** | `cat /etc/nv_tegra_release` | L4T R36.x |
| **Docker Engine funzionante** | `docker --version` | 24.x o superiore |
| **NVIDIA Container Toolkit** | `nvidia-ctk --version` | 1.x |
| **Runtime nvidia predefinito** | `docker info \| grep -i runtime` | `nvidia` presente |
| **SSD NVMe montato** | `df -h /mnt/storage` | ~931 GB disponibili |
| **Connessione internet attiva** | `curl -s https://github.com` | Risposta HTML |
| **Telecamere raggiungibili** | `ping 192.168.20.11` (×3) | Risposta |

> **IMPORTANTE — CONNESSIONE INTERNET**  
> Il primo avvio richiede connessione internet per scaricare l'immagine Docker
> di Frigate (~2 GB) e i modelli di supporto (LPR, Audio). Le telecamere
> funzionano in rete locale, ma il primo avvio no.

---

## Passo 1 — Generare la password MQTT

Il broker Mosquitto è configurato per rifiutare connessioni anonime.
Prima di avviare il sistema, generare le credenziali:

```bash
# Avviare un container temporaneo di Mosquitto per generare la password
docker run --rm -v $(pwd)/mosquitto/config:/mosquitto/config \
  eclipse-mosquitto:2 \
  mosquitto_passwd -b /mosquitto/config/pwfile sentinel sentinel_password
```

Sostituire `sentinel` e `sentinel_password` con utente e password a scelta.
Annotare i valori scelti: serviranno al Passo 2.

> **NOTA**: Il file `pwfile` esiste già vuoto nella cartella. Il comando
> sopra lo popola con le credenziali cifrate. NON cancellarlo prima.

---

## Passo 2 — Compilare il file `.env`

Copiare il file modello e compilare i campi:

```bash
cp .env.example .env
nano .env   # oppure l'editor che preferisci
```

### Campi da modificare obbligatoriamente

| Variabile | Cosa scrivere | Esempio |
|-----------|---------------|---------|
| `FRIGATE_IMAGE_SUFFIX` | `-tensorrt-jp6` | `-tensorrt-jp6` |
| `DOCKER_RUNTIME` | `nvidia` | `nvidia` |
| `STORAGE_RECORDINGS_PATH` | Percorso SSD per le registrazioni | `/mnt/storage/recordings` |
| `STORAGE_DB_PATH` | Percorso SSD per il database | `/mnt/storage/db` |
| `FRIGATE_MQTT_USER` | L'utente MQTT scelto al Passo 1 | `sentinel` |
| `FRIGATE_MQTT_PASSWORD` | La password MQTT scelta al Passo 1 | `sentinel_password` |
| `FRIGATE_CAM_*_URL` | Gli URL RTSP reali delle 3 telecamere | Vedere sotto |

### URL RTSP delle telecamere Reolink RLC-811A

Le telecamere Reolink usano questo schema URL:
```
rtsp://UTENTE:PASSWORD@IP:554/h264Preview_01_main   ← flusso 4K (registrazione)
rtsp://UTENTE:PASSWORD@IP:554/h264Preview_01_sub    ← flusso 640x360 (rilevamento IA)
```

Schema di rete previsto (VLAN 20):

| Dispositivo | IP Assegnato | Variabili nel .env / Note |
|-------------|--------------|---------------------------|
| **Telecamera Varco Carrabile** | `192.168.20.11` | `FRIGATE_CAM_VARCO_CARRABILE_MAIN_URL`, `..._SUB_URL` |
| **Telecamera Varco Pedonale** | `192.168.20.12` | `FRIGATE_CAM_VARCO_PEDONALE_MAIN_URL`, `..._SUB_URL` |
| **Telecamera Piazzale** | `192.168.20.13` | `FRIGATE_CAM_PIAZZALE_MAIN_URL`, `..._SUB_URL` |
| **Scheda Relè Waveshare 8-ch** | `192.168.20.20` | **Da assegnare staticamente da Alessio** (usato da Orch. Fase 2) |
| **Altoparlante Fanvil A233** | `192.168.20.21` | **Da assegnare staticamente da Alessio** (usato da Orch. Fase 2) |

> **ATTENZIONE**: Verificare utente e password RTSP dall'interfaccia web di
> ciascuna telecamera (Impostazioni → Rete → Avanzate → RTSP).

### Variabili che NON vanno toccate (già corrette)

| Variabile | Valore | Motivo |
|-----------|--------|--------|
| `FRIGATE_VERSION` | `0.17.2` | Versione bloccata di progetto |
| `TZ` | `Europe/Rome` | Fuso orario italiano |
| `FRIGATE_MQTT_HOST` | `mosquitto` | Nome del servizio Docker interno (NON un IP) |

---

## Passo 3 — Configurazione sito in `config/config.yml`

Il file è già predisposto. Le uniche verifiche/modifiche possibili sono:

### Accelerazione hardware FFmpeg (Consigliata su Jetson)
Per attivare la decodifica video su chip NVDEC (hardware), aprire `config/config.yml`
e decommentare le due righe all'inizio del file:

```yaml
# PRIMA (commentate):
# ffmpeg:
#   hwaccel_args: preset-jetson-h264

# DOPO (attive):
ffmpeg:
  hwaccel_args: preset-jetson-h264
```

---

## Passo 4 — Avvio del sistema e recupero credenziali

```bash
# 1. Creare le cartelle di storage su SSD se non esistono
mkdir -p /mnt/storage/recordings /mnt/storage/db

# 2. Avviare tutti i servizi
docker compose up -d

# 3. Seguire i log di avvio per verificare il completamento e recuperare la password
docker compose logs -f frigate
```

### ⚠️ PRIMO AVVIO — COMPORTAMENTO ATTESO

Al primo avvio si verificano i seguenti passaggi in sequenza:

1. **Download immagine**: Docker scarica l'immagine Frigate (~2 GB).
2. **Generazione Modello TensorRT**: Frigate compila il modello `yolov4-416.trt` sul chip GPU.
   - Durata: **3–5 minuti**.
   - Durante questa fase i log mostrano l'avanzamento della conversione e il sistema sembra fermo.
   - **NON riavviare o interrompere il container.**
3. **Completamento compilazione**: Le righe relative alla conversione del modello terminano,
   e riprende regolarmente l'elaborazione dei flussi video delle telecamere.
4. **Download modelli LPR e Audio**: Scaricati automaticamente in background (richiede internet).

### Recupero Credenziali Amministratore (Primo Accesso)

Frigate 0.17 genera al primissimo avvio una password casuale temporanea per l'utente `admin`
e la stampa nei log del container:

```bash
# Eseguire questo comando per leggere le credenziali generate:
docker compose logs frigate | grep -i "admin"
```

Nel log comparirà un messaggio con l'utente `admin` e la password iniziale generata.
**Annotare subito questa password.**

### Accesso all'interfaccia protetta

Aprire nel browser da un PC connesso alla stessa rete locale:
```
https://IP_JETSON:8971
```

> **⚠️ AVVISO IMPORTANTE: AVVISO DI SICUREZZA / CERTIFICATO NEL BROWSER**  
> Al primo accesso, il browser (Chrome, Edge, Firefox, Safari) mostrerà una schermata rossa
> o un avviso di sicurezza tipo *"La connessione non è privata"* o *"Potenziale rischio di sicurezza"*.  
> **È un comportamento del tutto NORMALE e previsto**: la porta 8971 cifra il traffico con
> un certificato HTTPS locale autofirmato generato direttamente da Frigate, che non è emesso da
> una Certification Authority pubblica di internet.  
> **Come procedere oltre**:  
> - Su **Google Chrome / Microsoft Edge**: cliccare su *"Avanzate"* in basso a sinistra e poi su *"Procedi su IP_JETSON (non sicuro)"*.  
> - Su **Mozilla Firefox**: cliccare su *"Avanzate..."* e poi su *"Accetta il rischio e continua"*.  
> Il sistema NON è rotto e NON c'è alcun pericolo: la connessione locale è protetta da cifratura TLS.
>
> Dopo aver superato l'avviso:  
> 1. Accedere inserendo l'utente `admin` e la password iniziale recuperata dal log.  
> 2. Appena entrati, andare su **Settings → Users** e impostare una password definitiva sicura (minimo 12 caratteri).  
> 3. **Nota bene**: La porta `5000` è bloccata su `127.0.0.1` e non è raggiungibile dalla LAN, proteggendo il sistema da accessi non autorizzati.


### Verifica dei Container e dell'Orchestratore Osservatore

Controllare che tutti e 3 i container siano attivi:
```bash
docker compose ps
```
Output atteso:
```text
NAME           STATUS
frigate        Up (healthy)
mosquitto      Up
orchestrator   Up
```

> **CHE COS'È L'ORCHESTRATORE IN QUESTA VERSIONE (FASE 1)**  
> Il servizio `orchestrator` incluso in questa cartella è un **osservatore diagnostico e nulla di più**.  
> - Si collega a Mosquitto con le stesse credenziali di Frigate.  
> - Si sottoscrive a `frigate/#` e registra ogni evento nel file `storage/logs/sentinel_events.log` in formato **JSON Lines (una riga JSON per evento)** con orario ISO 8601, topic e payload nativo.  
> - Ha un meccanismo di rotazione integrato (10 MB per file, max 5 file = max 50 MB su disco): non saturerà mai la memoria.  
> - Filtra automaticamente le immagini binarie salvando solo i metadati, impedendo il consumo indebito dello spazio.  
> - **NON comanda relè, NON invia comandi all'altoparlante, NON decide allarmi.**  
> *La logica di allarme, la voce, i relè e l'interfaccia utente arrivano nel prossimo aggiornamento della Fase 2, senza reinstallare nulla.*  
> Questo registro è fondamentale: permette a noi sviluppatori di verificare sul campo la corrispondenza esatta con il contratto degli eventi e di rigiocarli nei test.

Per verificare che l'orchestratore stia registrando gli eventi in tempo reale:
```bash
tail -f storage/logs/sentinel_events.log
```
Facendo passare una persona o un'auto davanti a una telecamera, compariranno immediatamente le righe JSON:  
`{"timestamp":"2026-09-07T12:00:00+02:00","topic":"frigate/events","payload_bytes":820,"type":"json","payload":{...}}`


---

## Passo 5 — Collaudo e Misurazioni

Passare alla [Checklist di Collaudo](CHECKLIST_COLLAUDO.md) ed eseguire le verifiche in campo.


---

## Misurazione Telemetria Hardware (Memoria e Temperatura)

Perché richiediamo queste misure?  
Il dimensionamento commerciale dell'hardware (scelta tra Jetson Orin Nano 8GB e Jetson Orin NX 16GB)
dipende dal comportamento termico e dal consumo reale di RAM con i 3 flussi 4K attivi a regime.  
Non possiamo simulare questo dato in laboratorio: serve la misura fisica sul campo.

### Come rilevare i dati con `tegrastats` (Strumento ufficiale JetPack)

Eseguire sul Jetson il comando:
```bash
sudo tegrastats
```

Il comando stamperà ogni secondo una riga con i parametri vitali:
```text
RAM 3420/7400MB (lfb 128x4MB) CPU [15%@729,12%@729,...] GR3D_FREQ 45%@624 APE 154 BPU 0%@0 ... tj@48.5C SOC@46.0C CPU@48.0C GPU@45.5C
```

- **RAM**: valore prima della barra (es. `3420MB` utilizzata su `7400MB` totali).
- **Temperatura**: campo `tj@XX.XC` (temperatura di giunzione) o `GPU@XX.XC` / `CPU@XX.XC`.

Premere `Ctrl+C` per uscire. Annotare i valori nella Sezione 8 della Checklist di Collaudo.

---

## Uso quotidiano

| Operazione | Comando |
|------------|---------|
| Avviare il sistema | `docker compose up -d` |
| Fermare il sistema | `docker compose down` |
| Vedere lo stato dei container | `docker compose ps` |
| Vedere i log in tempo reale | `docker compose logs -f frigate` |
| Vedere i log di Mosquitto | `docker compose logs -f mosquitto` |
| Riavviare solo Frigate | `docker compose restart frigate` |
| Controllare risorse e temperature | `sudo tegrastats` |

> **REGOLA DI SISTEMA**: Non aggiornare mai la versione di Frigate (`FRIGATE_VERSION`
> nel `.env`) senza l'autorizzazione dello sviluppatore. Un cambio di versione può
> modificare lo schema del database o la sintassi YAML rompendo il sistema.

---

## Risoluzione Problemi

### Tabella diagnostica

| Sintomo | Causa probabile | Azione | Competenza |
|---------|----------------|--------|------------|
| Container Frigate non parte | File `.env` non compilato | Compilare tutti i campi `DA_COMPILARE_*` | Alessio |
| `Error: Unable to open pwfile` | File password MQTT mancante | Eseguire il Passo 1 del manuale | Alessio |
| Telecamera offline (riquadro nero) | IP errato, switch PoE o cavo | Verificare IP, cavo di rete, alimentazione | Alessio |
| `Connection refused` su MQTT | Credenziali errate tra `.env` e `pwfile` | Verificare corrispondenza credenziali | Alessio |
| Rilevamenti assenti nei primi 5 min | Compilazione TensorRT in corso | Attendere fine generazione modello | Alessio |
| Porta 8971 non risponde | Frigate ancora in fase di inizializzazione | Controllare con `docker compose ps` | Alessio |
| Login fallito su porta 8971 | Password iniziale admin errata | Eseguire `docker compose logs frigate \| grep admin` | Alessio |
| Rilevamenti assenti dopo 10 min | Errore runtime GPU o configurazione | Inviare i log completi allo sviluppatore | **Sviluppatore** |
| `[detector] error` nei log | Problema driver o modello non caricato | Inviare i log completi allo sviluppatore | **Sviluppatore** |
| Errore parsing YAML all'avvio | Errore di formattazione in config.yml | Inviare config.yml e log allo sviluppatore | **Sviluppatore** |
| Targhe non lette su varco carrabile | Risoluzione sub 360p insufficiente | Regolare zoom 5x; se non basta, chiamare dev | **Sviluppatore** |
| Audio non rilevato | Microfono disattivato sulla telecamera | Abilitare audio nel menu Reolink | Alessio |

### Come estrarre e inviare i log allo sviluppatore

```bash
docker compose logs --tail=500 frigate > /tmp/frigate_log.txt
docker compose logs --tail=100 mosquitto > /tmp/mosquitto_log.txt
```
Inviare i due file generati allo sviluppatore.

---

## Schema di Rete Completo (VLAN 20 — 192.168.20.0/24)

Tutti i dispositivi dell'impianto risiedono sulla medesima sottorete dedicata:

```text
Router / Switch PoE (Gateway: 192.168.20.1)
  │
  ├── 192.168.20.10  Jetson Orin Nano (Sentinel AI Engine: Frigate + Mosquitto)
  │
  ├── 192.168.20.11  Reolink RLC-811A Varco Carrabile (RTSP: 554)
  ├── 192.168.20.12  Reolink RLC-811A Varco Pedonale  (RTSP: 554)
  ├── 192.168.20.13  Reolink RLC-811A Piazzale        (RTSP: 554)
  │
  ├── 192.168.20.20  Scheda Relè Waveshare 8-ch Modbus/TCP (Configurata da Alessio)
  └── 192.168.20.21  Altoparlante IP Fanvil A233 SIP/IP     (Configurato da Alessio)
```

> **NOTA PER ALESSIO**:  
> Assegna gli indirizzi statici `192.168.20.20` e `192.168.20.21` direttamente sui dispositivi
> Waveshare e Fanvil durante il cablaggio. Frigate non interagisce direttamente con essi,
> ma l'orchestratore della Fase 2 si collegherà esattamente a quegli IP.


## Registro biometrico ORIN (viso + voce)

1. Sblocca la dashboard con il **PIN Manutentore**. Al primo avvio, se non c'è nessuna identità registrata, si apre da sola la configurazione iniziale (campi già compilati per Alessio Russo).
2. **Volto**: «Avvia fotocamera», allinea il volto al mirino ovale, «Cattura Volto» (countdown 3-2-1). Puoi rifare lo scatto.
3. **Voce**: «Registra (4 s)» e pronuncia *«Sono Alessio Russo, autorizzazione per ORIN»*. Riascolta prima di salvare.
4. «Salva identità». Il profilo finisce in `config/biometrics/` (`profiles.json`, `faces/`, `voices/`) e l'orchestratore lo usa subito, senza riavvio.
5. Altre identità (es. il Presidente): dock **Identità** → «+ Aggiungi Nuova Identità». Revoca dallo stesso elenco.

Nota: fotocamera e microfono del browser funzionano solo su **localhost** o **HTTPS**. Dal Jetson usa `http://localhost:8080`; da smartphone serve HTTPS.
