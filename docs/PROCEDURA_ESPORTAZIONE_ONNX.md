# PROCEDURA DI ESPORTAZIONE MODELLO D-FINE IN FORMATO ONNX

Questo documento descrive la procedura tecnica per generare ed esportare il modello **D-FINE Nano** in formato `.onnx`, nel caso sia necessario rigenerarlo in futuro per aggiornamenti o modifiche architetturali.

> **NOTA PER LA PRODUZIONE**:  
> Il file pre-esportato `dfine_n.onnx` (15,25 MB) è **già incluso** nella cartella `config/model_cache/`.  
> Il tecnico installatore (Alessio) non deve eseguire questa procedura.

---

## 1. Dati Tecnici del Modello Consegnato
*   **Architettura**: D-FINE Nano (backbone HGNetv2-N).
*   **Repository ufficiale**: `https://github.com/Peterande/D-FINE` (Commit release COCO).
*   **Configurazione esatta**: `configs/dfine/dfine_hgnetv2_n_coco.yml`
*   **Checkpoint pesi pre-addestrati**: `dfine_n_coco.pth` (dataset COCO 80 classi).
*   **Risoluzione di input**: $640 \times 640$ pixel (formato tensore NCHW, RGB, float32).
*   **Licenza**: **Apache 2.0** (libera per uso e distribuzione commerciale a codice chiuso).
*   **Dimensione file `.onnx`**: **15.258.358 byte (~15,26 MB)**.
*   **Posizione nel progetto**: `config/model_cache/dfine_n.onnx`

---

## 2. Metodo 1: Esportazione tramite Docker (Multi-stage Build)
Su un sistema dotato di Docker (Linux o PC con Docker Desktop), eseguire il seguente comando nella radice del progetto:

```bash
docker build . --rm --output ./config/model_cache -f- << 'EOF'
FROM python:3.11-slim AS build
RUN apt-get update && apt-get install --no-install-recommends -y git libgl1 libglib2.0-0 wget && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.0 /uv /bin/
WORKDIR /dfine
RUN git clone https://github.com/Peterande/D-FINE.git .
RUN uv pip install --no-cache --system torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN uv pip install --no-cache --system -r requirements.txt
RUN uv pip install --no-cache --system onnx huggingface_hub

# Download checkpoint ufficiale D-FINE Nano COCO
RUN wget -O dfine_n_coco.pth https://github.com/Peterande/D-FINE/releases/download/v1.0/dfine_n_coco.pth || \
    python3 -c "from huggingface_hub import hf_hub_download; hf_hub_download('Peterande/D-FINE', 'dfine_n_coco.pth', local_dir='.')"

# Esportazione ONNX con semplificazione del grafo e verifica
RUN python3 tools/deployment/export_onnx.py -c configs/dfine/dfine_hgnetv2_n_coco.yml -r dfine_n_coco.pth --check

FROM scratch
COPY --from=build /dfine/dfine_n_coco.onnx /dfine_n.onnx
EOF
```

---

## 3. Metodo 2: Esportazione in Ambiente Virtuale Python (Locale)
In alternativa a Docker, se si dispone di Python 3.10+:

```bash
git clone https://github.com/Peterande/D-FINE.git
cd D-FINE
python -m venv .venv
source .venv/bin/activate  # su Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install onnx onnxsim

# Scaricare il checkpoint dfine_n_coco.pth
# ed eseguire l'esportazione:
python tools/deployment/export_onnx.py \
  -c configs/dfine/dfine_hgnetv2_n_coco.yml \
  -r dfine_n_coco.pth \
  --check

# Copiare il file esportato nella cartella del progetto:
cp dfine_n_coco.onnx ../config/model_cache/dfine_n.onnx
```

---

## 4. Metodo 3: Download Diretto da Hub Certificato
L'esportazione standard ONNX ufficiale di D-FINE Nano COCO è mantenuta su Hugging Face Hub sotto `onnx-community/dfine_n_coco-ONNX`:

```bash
curl -L "https://huggingface.co/onnx-community/dfine_n_coco-ONNX/resolve/main/onnx/model.onnx" -o config/model_cache/dfine_n.onnx
```
Dimensione verificata: `15.258.358 byte`.
Checksum SHA-256 verificabile con `certutil -hashfile config/model_cache/dfine_n.onnx SHA256`.
