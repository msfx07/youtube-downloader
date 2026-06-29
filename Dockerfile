FROM python:3.11-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py downloader.py ./
COPY templates/ templates/
COPY static/ static/

VOLUME ["/downloads"]
EXPOSE 5000

ENTRYPOINT ["gunicorn", "-w", "1", "-k", "gevent", "app:app", "--bind", "0.0.0.0:5000"]
