FROM python:3.11-slim

# Evita la scrittura di file .pyc e forza il flush immediato di stdout/stderr nei log
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# tzdata: supporto del fuso orario (es. TZ=Europe/Rome), circa 3-4 MB su disco.
# ffmpeg: OBBLIGATORIO per la dissuasione vocale. L'altoparlante Fanvil A233 viene
#         pilotato in MULTICAST RTP (G.711 mu-law verso 239.255.1.1:5004), quindi
#         speaker_controller.py invoca direttamente il binario ffmpeg/ffprobe.
#         Senza questo pacchetto gli annunci non vengono riprodotti.
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia e installazione dipendenze minimali
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutti gli script Python dell'orchestratore (observer, relay, speaker, nas)
COPY *.py .

# Cartella di destinazione per i registri eventi montata dall'host
VOLUME ["/app/logs"]

CMD ["python3", "observer.py"]
