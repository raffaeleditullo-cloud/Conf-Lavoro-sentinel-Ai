FROM python:3.11-slim

# Evita la scrittura di file .pyc e forza il flush immediato di stdout/stderr nei log
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ffmpeg: necessario anche qui perche' il pulsante "dissuasione vocale" della
# dashboard usa lo stesso driver speaker_controller.py dell'orchestratore, che
# diffonde l'audio via MULTICAST RTP sull'altoparlante Fanvil A233.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dipendenze dei driver hardware condivisi (montati a runtime su /app/drivers)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia i file dell'interfaccia (index.html, assets, server.py)
COPY . /app

EXPOSE 8080

CMD ["python3", "-u", "server.py"]
