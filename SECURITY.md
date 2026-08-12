# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest (`master`) | ✅ Active |

## Reporting a Vulnerability

If you discover a security vulnerability, **please do not open a public issue.**

Instead, report it privately via email to: **security@sandbox99.cc**

You should receive a response within **72 hours**. We will work with you to understand and address the issue before any public disclosure.

## Security Measures

This project implements the following security controls:

### Rate Limiting
- **5 downloads per hour** per IP address
- **10 file retrievals per hour** per IP address
- Global default: 200 requests/day, 60 requests/hour
- Powered by [Flask-Limiter](https://flask-limiter.readthedocs.io/) with in-memory storage

### Input Validation
- All user inputs validated against strict allowlists (resolution, format, audio mode)
- Only YouTube URLs accepted: `youtube.com`, `www.youtube.com`, `youtu.be`, `m.youtube.com`
- HTTPS-only — plain HTTP requests are rejected
- Playlist parameters stripped — only individual videos are downloaded
- Job IDs validated as UUIDs on all route parameters

### Security Headers
Every response includes:
- `Content-Security-Policy` — restricts script/style/image/connect sources
- `X-Content-Type-Options: nosniff` — prevents MIME type sniffing
- `X-Frame-Options: DENY` — prevents clickjacking
- `X-XSS-Protection: 1; mode=block` — legacy XSS filter
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy` — disables camera, microphone, geolocation

### Container Security
- Runs as non-root user (`appuser`) inside the container
- Download directory created with restricted permissions
- Minimal base image (`python:3.11-slim`)
- **Docker Compose hardening:**
  - Read-only root filesystem (`read_only: true`)
  - Tmpfs for `/tmp` with `noexec,nosuid` and 64 MB size limit
  - All Linux capabilities dropped (`cap_drop: ALL`)
  - Privilege escalation blocked (`no-new-privileges: true`)
  - Memory limit enforced (512 MB)
  - Explicit UID:GID override (`user: "1000:1000"`)

### Resource Limits
- Maximum concurrent downloads: **10** (enforced via semaphore)
- Maximum file size: **2 GB** (enforced via yt-dlp)
- Automatic cleanup: abandoned jobs deleted after 1 hour
- Files deleted 5 seconds after being served

### Error Handling
- Detailed error messages logged server-side only
- Generic error messages returned to clients (no internal paths or stack traces)

### Subresource Integrity (SRI)
- Third-party scripts loaded with `integrity` and `crossorigin` attributes
- Prevents execution if the remote script is tampered with

### Dependency Security
- Production dependencies pinned with minimum versions in `requirements.txt`
- Check for known vulnerabilities regularly:
  ```bash
  pip-audit
  ```

## Configuration

Security-relevant environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_DEBUG` | `false` | Set to `true` only for local development |
| `DOWNLOADS_DIR` | `/downloads` | Temporary download storage path |

## Best Practices for Deployment

1. **Always deploy behind a TLS-terminating reverse proxy** (Caddy, nginx, etc.)
2. **Do not expose port 5000 directly** to the internet
3. **Set `FLASK_DEBUG=false`** (or omit it) in production
4. **Monitor the `/health` endpoint** for uptime checks
5. **Keep dependencies updated** — run `pip-audit` periodically
6. **Review Docker image** — rebuild regularly to pick up base image security patches

## Security Checklist

- [ ] No hardcoded secrets or API keys in source code
- [ ] All user inputs validated with allowlists
- [ ] Rate limiting enabled on download and file endpoints
- [ ] Security headers present on all responses
- [ ] Container runs as non-root user
- [ ] Container hardened: read-only fs, cap_drop ALL, no-new-privileges, memory limit
- [ ] SRI hashes on all external scripts
- [ ] Error messages sanitized (no internal details leaked)
- [ ] TLS enabled via reverse proxy
- [ ] Debug mode disabled in production
- [ ] Healthcheck uses `python3` (no `curl` dependency in slim image)
