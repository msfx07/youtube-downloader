FROM python:3.11-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -r -s /usr/sbin/nologin appuser

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py downloader.py ./
COPY templates/ templates/
COPY static/ static/

RUN mkdir -p /downloads && chown appuser:appuser /downloads

VOLUME ["/downloads"]
EXPOSE 5000

USER appuser

ENTRYPOINT ["gunicorn", "-w", "1", "-k", "gevent", "app:app", "--bind", "0.0.0.0:5000"]
