FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY static/ ./static/

RUN mkdir -p /var/cache/network-ai && \
    chown -R appuser:appuser /var/cache/network-ai && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 3000

CMD ["gunicorn", "backend.main:app", "-c", "backend/gunicorn_config_fixed.py"]