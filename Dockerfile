# =============================================================================
# SIGMA-9 Micro-Doppler Radar Target Classification — production image
# =============================================================================
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files / buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps needed to build psycopg2 and provide healthcheck curl
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as a non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/healthz || exit 1

# eventlet worker required for Flask-SocketIO's WebSocket support under gunicorn.
# -w 1 : SocketIO with in-memory pub/sub needs a single worker unless a
#        message_queue (Redis) is configured — see config.py / REDIS_URL.
CMD ["sh", "-c", "gunicorn -k eventlet -w 1 --bind 0.0.0.0:${PORT} --timeout 120 app:app"]
