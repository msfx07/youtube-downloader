# YouTube Downloader

> Self-hosted YouTube downloader with a browser UI — runs entirely on localhost via Docker. No cloud, no accounts, no tracking.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-black.svg)](https://flask.palletsprojects.com/)
[![Docker Compose](https://img.shields.io/badge/Docker%20Compose-v2-blue.svg)](https://docs.docker.com/compose/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

**Live demo:** [https://ytd.sandbox99.cc](https://ytd.sandbox99.cc)

---

## Table of Contents

- [Branches](#branches)
- [Quick Start](#quick-start)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Features](#features)
- [Architecture](#architecture)
- [Dependencies](#dependencies)
- [License](#license)

---

## Branches

| Branch | Interface | How to run |
|---|---|---|
| `master` | Browser UI (localhost only) | `docker-compose up` |
| `youtube-downloader-web` | Browser UI (+ Caddy HTTPS) | `docker-compose up` |

---

## Quick Start

### Requirements

- Docker + Docker Compose

### Start

```bash
docker-compose up --build
```

Open [http://localhost:5000](http://localhost:5000).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Flask 3.x |
| Download engine | yt-dlp |
| Post-processing | FFmpeg |
| Server | Gunicorn + gevent |
| Frontend | Vanilla JS + CSS (no CDN) |
| Container | Docker + Docker Compose |

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
- **Rate limiting:** no rate limit on localhost. Rate limiting (`5 downloads/hour`, `10 file serves/hour` per IP) applies only on the public-facing deployment (`youtube-downloader-web` branch with Caddy)

---

## Architecture

- Each download runs in an isolated temp dir: `/downloads/<job_id>/`.
- **File cleanup:** deleted 5s after the file is served via "Save Download".
- **Abandoned job cleanup:** background thread runs every 15 min, deletes jobs older than 1h (covers errors, cancels, and uncollected downloads).
- **URL validation:** HTTPS only · accepted domains: `youtube.com`, `www.youtube.com`, `youtu.be`, `m.youtube.com`.
- **SSE events:** `{"type": "progress"|"finished"|"error"|"cancelled", ...}` — browser reads from `/stream/<job_id>`.
- **Single worker:** gunicorn `-w 1` + gevent. All routes share one in-memory job store — do not increase workers without adding a shared store (Redis, etc.).

---

## Dependencies

Python 3.11, yt-dlp, FFmpeg, Flask, gunicorn, gevent.

---

## License

[MIT](./LICENSE)
