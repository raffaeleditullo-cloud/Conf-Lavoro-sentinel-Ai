FROM python:3.11-slim

# Evita la scrittura di file .pyc e forza il flush immediato di stdout/stderr nei log
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Installazione del pacchetto tzdata per il supporto del fuso orario (es. TZ=Europe/Rome).
# tzdata in Debian occupa circa 3-4 MB su disco senza dipendenze pesanti.
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
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
