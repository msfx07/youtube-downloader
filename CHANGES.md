# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Rate limiting** — 5 downloads/hour and 10 file retrievals/hour per IP via Flask-Limiter
- **Security headers** on all responses: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, X-XSS-Protection
- **Subresource Integrity (SRI)** hashes on the analytics script across all templates
- **Concurrent download limit** — max 10 simultaneous downloads via threading semaphore
- **Maximum file size** — 2 GB limit enforced via yt-dlp
- **UUID validation** on all `/<job_id>` route parameters (stream, cancel, file)
- **`/health` endpoint** — returns active download count and max concurrency for monitoring
- **Docker healthcheck** — `/health` polled every 30s via Python (no `curl` dependency in slim image)
- **Non-root container user** — Dockerfile now runs as `appuser` instead of root
- **Docker Compose hardening** — read-only root filesystem, tmpfs `/tmp` (noexec/nosuid, 64 MB), all capabilities dropped, no-new-privileges, 512 MB memory limit, explicit UID:GID
- **`SECURITY.md`** — security policy, vulnerability reporting, and deployment checklist
- **`CHANGES.md`** — this changelog

### Changed
- Error messages sent to clients are now generic ("Download failed. Please check the URL and try again.") — detailed errors logged server-side only
- `FLASK_DEBUG` environment variable controls debug mode (defaults to `false`); `app.run(debug=True)` removed
- `docker-compose.yml` includes healthcheck configuration and full container hardening
- `requirements.txt` and `requirements-dev.txt` include `flask-limiter>=3.5`
- Test suite updated: all job IDs are valid UUIDs; error message assertions match sanitized output

### Fixed
- Semaphore leak when job disappears between thread start and download begin
- Security review findings from 2026-08-12 (see `SECURITY.md` for full details)
