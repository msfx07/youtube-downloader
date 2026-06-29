# YouTube Downloader

Containerized YouTube downloader — available in three flavours:

| Branch | Interface | How to run |
|---|---|---|
| `master` | Browser UI (localhost only) | `docker-compose up` |
| `youtube-downloader-web` | Browser UI (+ Caddy HTTPS) | `docker-compose up` |

---

## Localhost App (this branch)

Runs on `localhost:5000` — no reverse proxy, no TLS. For local use only.

### Requirements

- Docker + Docker Compose

### Start

```bash
docker-compose up --build
```

Open [http://localhost:5000](http://localhost:5000).

---

## Project Structure

```
youtube-downloader/
├── app.py              # Flask app: routes, SSE, job store, cleanup thread
├── templates/
│   └── index.html      # Single-page UI (vanilla JS + CSS, no CDN)
├── static/
│   ├── index.js        # Minified frontend JS
│   ├── style.css       # Minified CSS
│   └── theme.js        # Theme toggle
├── requirements.txt    # Production deps
├── Dockerfile          # python:3.11-slim + ffmpeg + gunicorn entrypoint
└── docker-compose.yml  # Port 5000 + /downloads volume
```

---

## Features

- **Resolutions:** best, 1080p, 720p, 480p
- **Formats:** mp4, mkv, webm
- **Audio-only:** mp3, m4a, opus (mutually exclusive with resolution/format)
- **Playlist protection:** playlist params (`list`, `index`, `start_radio`, `pp`) stripped automatically — always downloads a single video
- **Cancel:** stop an in-progress download at any time (best-effort — cannot interrupt FFmpeg post-processing)
- **Form lock:** resolution, format, audio, and URL inputs disable while download is active

---

## Architecture

- Each download runs in an isolated temp dir: `/downloads/<job_id>/`.
- **File cleanup:** deleted 5s after the file is served via "Save Download".
- **Abandoned job cleanup:** background thread runs every 15 min, deletes jobs older than 1h (covers errors, cancels, and uncollected downloads).
- **Rate limiting:** `POST /download` 5/hour per IP · `GET /file` 10/hour per IP. Returns `{"error": "Rate limit exceeded. Try again later."}` on 429.
- **URL validation:** HTTPS only · accepted domains: `youtube.com`, `www.youtube.com`, `youtu.be`, `m.youtube.com`.
- **SSE events:** `{"type": "progress"|"finished"|"error"|"cancelled", ...}` — browser reads from `/stream/<job_id>`.
- **Single worker:** gunicorn `-w 1` + gevent. All routes share one in-memory job store — do not increase workers without adding a shared store (Redis, etc.).

---

## Dependencies

Python 3.11, yt-dlp, FFmpeg, Flask, Flask-Limiter, gunicorn, gevent.
