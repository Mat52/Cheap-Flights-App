FROM python:3.10-slim

# Instalacja zależności systemowych potrzebnych do Playwrighta + GUI
RUN apt-get update && apt-get install -y \
    wget gnupg curl unzip x11-utils xvfb \
    libnss3 libatk-bridge2.0-0 libgtk-3-0 libasound2 \
    libxss1 libxcomposite1 libxrandr2 libgbm1 \
    libxdamage1 libxext6 libxfixes3 libx11-xcb1 libxcb1 \
    fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Ustawienie katalogu roboczego
WORKDIR /app

# Kopiowanie plików aplikacji
COPY ./app /app
WORKDIR /app
COPY requirements.txt .
COPY docker/entrypoint.sh /app/entrypoint.sh

# Ścieżka do aplikacji
ENV PYTHONPATH=/app

# Instalacja zależności Pythona
RUN pip install --upgrade pip && pip install -r requirements.txt

# Instalacja przeglądarek Playwrighta wraz z zależnościami
RUN python -m playwright install --with-deps

# Nadanie uprawnień do skryptu startowego
RUN chmod +x /app/entrypoint.sh

# Domyślny punkt wejścia
ENTRYPOINT ["bash", "/app/entrypoint.sh"]
