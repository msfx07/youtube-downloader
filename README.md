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

- [Branch](#branch)
- [Quick Start](#quick-start)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Features](#features)
- [Architecture](#architecture)
- [Security](#security)
- [Dependencies](#dependencies)
- [Troubleshooting](#troubleshooting)
- [Changelog](#changelog)
- [License](#license)

---

## Branch

| Branch | Interface | How to run |
|---|---|---|
| `master` | Browser UI (localhost) | `docker-compose up` |

---

## Quick Start

### Requirements

- Docker + Docker Compose

### Local Development

```bash
docker-compose up --build
```

Opens at [http://localhost:5000](http://localhost:5000). No TLS, no hardening — just for local testing.

### Production Options

| Scenario | Command | TLS | Notes |
|----------|---------|-----|-------|
| **Own reverse proxy** | `docker compose -f docker-compose.prod.yml up --build -d` | Your proxy handles it | Use this if you already have Caddy, nginx, etc. on the host |
| **Built-in Caddy (new)** | `docker compose -f docker-compose.caddy.yml up --build -d` | Auto Let's Encrypt | Best for new deployments — Caddy container included |
| **Local testing (Caddy)** | `docker compose -f docker-compose.caddy.yml up --build -d` | Self-signed (`localhost`) | Edit `Caddyfile` to replace `localhost` with your domain before deploying |

**Caddy deployment steps:**
1. Edit `Caddyfile` — replace `localhost` with your domain, remove `tls internal`, set your email
2. Run `docker compose -f docker-compose.caddy.yml up --build -d`
3. Caddy auto-provisions a Let's Encrypt certificate

The `docker-compose.prod.yml` and `docker-compose.caddy.yml` share the same hardened web container (read-only filesystem, non-root user, memory limits, dropped capabilities). The difference is that `caddy` adds a Caddy container for TLS termination and security headers.

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
├── app.py                  # Flask app: routes, SSE, job store, cleanup thread
├── downloader.py           # yt-dlp download logic (CLI + library)
├── templates/
│   ├── index.html          # Single-page UI (vanilla JS + CSS)
│   ├── 404.html            # Custom 404 page
│   └── policy.html         # Fair use policy page
├── static/
│   ├── index.js            # Frontend JS (form, SSE, progress)
│   ├── style.css           # Styles (dark/light theme)
│   └── theme.js            # Theme toggle
├── tests/
│   ├── test_app.py         # Flask route & integration tests
│   └── test_downloader.py  # Downloader unit tests
├── requirements.txt        # Production deps
├── requirements-dev.txt    # Dev/test deps
├── Dockerfile              # python:3.11-slim + ffmpeg + gunicorn
├── docker-compose.yml      # Local dev (port 5000, no hardening)
├── docker-compose.prod.yml # Production hardened (your own reverse proxy)
├── docker-compose.caddy.yml # Production + built-in Caddy (TLS, headers, SSE)
├── Caddyfile               # Caddy config (edit domain + email before deploy)
├── .dockerignore           # Build context exclusions
├── SECURITY.md             # Security policy & deployment checklist
├── CHANGES.md              # Changelog
└── LICENSE                 # MIT
```

---

## Features

- **Resolutions:** best, 1080p, 720p, 480p
- **Formats:** mp4, mkv, webm
- **Audio-only:** mp3, m4a, opus (mutually exclusive with resolution/format)
- **Playlist protection:** playlist params (`list`, `index`, `start_radio`, `pp`) stripped automatically — always downloads a single video
- **Cancel:** stop an in-progress download at any time (best-effort — cannot interrupt FFmpeg post-processing)
- **Form lock:** resolution, format, audio, and URL inputs disable while download is active
- **Rate limiting:** 5 downloads/hour, 10 file serves/hour per IP (via Flask-Limiter). Global defaults: 200/day, 60/hour.

---

## Architecture

- Each download runs in an isolated temp dir: `/downloads/<job_id>/`.
- **File cleanup:** deleted 5s after the file is served via "Save Download".
- **Abandoned job cleanup:** background thread runs every 15 min, deletes jobs older than 1h (covers errors, cancels, and uncollected downloads).
- **URL validation:** HTTPS only · accepted domains: `youtube.com`, `www.youtube.com`, `youtu.be`, `m.youtube.com`.
- **SSE events:** `{"type": "progress"|"finished"|"error"|"cancelled", ...}` — browser reads from `/stream/<job_id>`.
- **Single worker:** gunicorn `-w 1` + gevent. All routes share one in-memory job store — do not increase workers without adding a shared store (Redis, etc.).
- **Concurrent downloads:** max 10 simultaneous downloads (semaphore). Excess requests receive a "server busy" error.
- **Max file size:** 2 GB per download (enforced via yt-dlp).
- **Container security:** runs as non-root user (`appuser`), read-only root filesystem, all capabilities dropped, no-new-privileges, 512 MB memory limit. See [SECURITY.md](./SECURITY.md) for full details.

---

## Security

This project follows security best practices for a self-hosted web application:

- **Rate limiting** — Flask-Limiter enforces per-IP limits on all endpoints
- **Security headers** — CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- **SRI** — third-party scripts loaded with Subresource Integrity hashes
- **Non-root container** — Dockerfile runs as `appuser`, not root
- **Input validation** — strict allowlists on all user inputs
- **Error sanitization** — generic messages to clients, detailed errors only in server logs
- **UUID validation** — all job ID route parameters validated as UUIDs
- **Resource limits** — concurrent download cap and max file size

See [SECURITY.md](./SECURITY.md) for the full security policy, vulnerability reporting process, and deployment checklist.

---

## Dependencies

Python 3.11, yt-dlp, FFmpeg, deno, Flask 3.x, Flask-Limiter, gunicorn, gevent, Caddy (optional).

---

## Troubleshooting

### Docker build fails: `i/o timeout` pulling base image

**Error:**
```
failed to solve: python:3.11-slim: ... dial tcp X.X.X.X:443: i/o timeout
```

Docker Hub is reachable but a specific IP timed out (Docker Hub is multi-IP; one may be flaky). Usually transient.

**Fix:**

1. Verify Docker Hub is reachable from your server:
   ```bash
   curl -v https://registry-1.docker.io/v2/
   ```
   Expected response: `HTTP/2 401` — means network is fine, Docker Hub is up.

2. Pull the base image directly to force a retry:
   ```bash
   docker pull python:3.11-slim
   ```

3. If still failing, restart the Docker daemon (clears DNS/connection cache):
   ```bash
   sudo systemctl restart docker
   docker compose up --build -d
   ```

---

## Changelog

See [CHANGES.md](./CHANGES.md) for a full list of changes.

---

## License

[MIT](./LICENSE)
