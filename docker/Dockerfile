# syntax=docker/dockerfile:1

# ---------- Stage 1: builder ----------
# Installs Python dependencies into an isolated virtualenv; only the finished
# venv is copied into the runtime image, leaving pip caches and build
# artifacts behind.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copied ahead of the application code so this (slowest) layer is only
# rebuilt when dependencies change, not on every code change.
COPY requirements.txt .
RUN pip install -r requirements.txt


# ---------- Stage 2: runtime ----------
FROM python:3.12-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=5000

COPY --from=builder /opt/venv /opt/venv

# Chromium only; --with-deps pulls in the system libraries it needs. The app
# runs headless, so no Xvfb/GUI packages. Runs as root (apt), before USER.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user rather than root.
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --chown=app:app ./app /app
USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/healthz', timeout=4)"

# Single worker, multiple threads: the search job registry (JOBS in
# webapp.py) lives in process memory, so separate workers wouldn't see each
# other's searches. With threaded workers --timeout only bounds the worker
# heartbeat; scraping itself runs in a background thread.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 120 --access-logfile - webapp:app"]
