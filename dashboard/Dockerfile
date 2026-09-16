FROM python:3.11-slim

# Evita la scrittura di file .pyc e forza il flush immediato di stdout/stderr nei log
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dipendenze dei driver hardware condivisi (montati a runtime su /app/drivers)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia i file dell'interfaccia (index.html, assets, server.py)
COPY . /app

EXPOSE 8080

CMD ["python3", "-u", "server.py"]
