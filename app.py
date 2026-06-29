#!/usr/bin/env python3
"""Flask web interface for YouTube downloader."""

import json
import logging
import os
import queue
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from typing import Generator
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

from flask import Flask, Response, jsonify, render_template, request, send_file
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from downloader import DownloadConfig, build_options
import yt_dlp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


@app.errorhandler(RateLimitExceeded)
def rate_limit_handler(e: RateLimitExceeded) -> tuple[Response, int]:
    return jsonify({"error": "Rate limit exceeded. Try again later."}), 429

DOWNLOADS_DIR = Path(os.environ.get("DOWNLOADS_DIR", "/downloads"))
JOB_TTL = 3600       # seconds before job is cleaned up
CLEANUP_INTERVAL = 900  # seconds between cleanup runs


@dataclass
class JobState:
    status: str                  # "running" | "finished" | "error" | "cancelled"
    queue: Queue
    filepath: Path | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    cancel_event: threading.Event = field(default_factory=threading.Event)


jobs: dict[str, JobState] = {}
jobs_lock = threading.Lock()


def _cleanup_old_jobs() -> None:
    while True:
        time.sleep(CLEANUP_INTERVAL)
        cutoff = time.time() - JOB_TTL
        with jobs_lock:
            expired = [jid for jid, j in jobs.items() if j.created_at < cutoff]
        for jid in expired:
            job_dir = DOWNLOADS_DIR / jid
            shutil.rmtree(job_dir, ignore_errors=True)
            with jobs_lock:
                jobs.pop(jid, None)
        if expired:
            logger.info("Cleaned up %d expired jobs", len(expired))


_cleanup_thread = threading.Thread(target=_cleanup_old_jobs, daemon=True)
_cleanup_thread.start()


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/policy")
def policy() -> str:
    return render_template("policy.html")


@app.errorhandler(404)
def not_found(e: Exception) -> tuple[str, int]:
    return render_template("404.html"), 404


VALID_RESOLUTIONS = {"best", "1080p", "720p", "480p"}
VALID_FORMATS = {"mp4", "mkv", "webm"}
VALID_AUDIO_ONLY = {None, "mp3", "m4a", "opus"}
VALID_DOMAINS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}

_PLAYLIST_PARAMS = {"list", "index", "start_radio", "pp"}


def _strip_playlist_params(url: str) -> str:
    parsed = urlparse(url)
    filtered = [(k, v) for k, v in parse_qsl(parsed.query) if k not in _PLAYLIST_PARAMS]
    clean_query = urlencode(filtered)
    return urlunparse(parsed._replace(query=clean_query))


def _validate_request(data: dict) -> tuple[str, DownloadConfig] | tuple[None, str]:
    url = data.get("url", "")
    if not isinstance(url, str) or not url.startswith("https://"):
        return None, "Only YouTube URLs accepted"
    parts = url.split("/")
    domain = parts[2] if len(parts) > 2 else ""
    if domain not in VALID_DOMAINS:
        return None, "Only YouTube URLs accepted"

    url = _strip_playlist_params(url)

    resolution = data.get("resolution", "best")
    if resolution not in VALID_RESOLUTIONS:
        return None, f"Invalid resolution: {resolution}"

    fmt = data.get("format", None)
    if fmt is not None and fmt not in VALID_FORMATS:
        return None, f"Invalid format: {fmt}"

    audio_only = data.get("audio_only", None)
    if audio_only not in VALID_AUDIO_ONLY:
        return None, f"Invalid audio_only: {audio_only}"

    if audio_only is not None and resolution != "best":
        return None, "audio_only cannot combine with resolution"
    if audio_only is not None and fmt is not None:
        return None, "audio_only cannot combine with format"

    if fmt is None:
        fmt = "mp4"

    config = DownloadConfig(resolution=resolution, format=fmt, audio_only=audio_only)
    return url, config


def _progress_hook(d: dict, job: "JobState") -> None:
    if d["status"] != "downloading":
        return
    if job.cancel_event.is_set():
        raise yt_dlp.utils.DownloadCancelled("Cancelled by user")
    percent_str = d.get("_percent_str", "0%").strip().rstrip("%")
    try:
        percent = float(percent_str)
    except ValueError:
        percent = 0.0
    job.queue.put({
        "type": "progress",
        "percent": percent,
        "speed": d.get("_speed_str", "").strip(),
        "eta": d.get("eta", 0),
    })


def _run_download(job_id: str, url: str, config: DownloadConfig) -> None:
    job_dir = DOWNLOADS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return

    opts = build_options(job_dir, config)
    opts["progress_hooks"] = [lambda d: _progress_hook(d, job)]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        # find actual file (not prepare_filename — it's pre-postprocessor)
        ext = config.audio_only if config.audio_only else config.format
        files = sorted(job_dir.glob(f"*.{ext}"))
        filepath = files[0] if files else job_dir / f"download.{ext}"

        with jobs_lock:
            job.status = "finished"
            job.filepath = filepath
        job.queue.put({"type": "finished", "filename": filepath.name})

    except yt_dlp.utils.DownloadCancelled:
        with jobs_lock:
            job.status = "cancelled"
        job.queue.put({"type": "cancelled"})
        logger.info("Job %s cancelled by user", job_id)

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error("Download failed for job %s: %s", job_id, error_msg)
        with jobs_lock:
            job.status = "error"
            job.error = error_msg
        job.queue.put({"type": "error", "message": error_msg})

    except Exception as e:
        logger.exception("Unexpected error in job %s: %s", job_id, e)
        with jobs_lock:
            job.status = "error"
            job.error = "Internal server error"
        job.queue.put({"type": "error", "message": "Internal server error"})


@app.post("/download")
@limiter.limit("5/hour")
def start_download() -> Response:
    data = request.get_json(silent=True) or {}
    result = _validate_request(data)

    if result[0] is None:
        logger.warning("Invalid download request: %s", result[1])
        return jsonify({"error": result[1]}), 400

    url, config = result
    job_id = str(uuid.uuid4())

    with jobs_lock:
        jobs[job_id] = JobState(status="running", queue=Queue())

    thread = threading.Thread(
        target=_run_download, args=(job_id, url, config), daemon=True
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.get("/stream/<job_id>")
def stream(job_id: str) -> Response:
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    def generate() -> Generator[str, None, None]:
        while True:
            try:
                event = job.queue.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("finished", "error", "cancelled"):
                    break
            except queue.Empty:
                yield 'data: {"type": "keepalive"}\n\n'

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/cancel/<job_id>")
def cancel_download(job_id: str) -> Response:
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job.status != "running":
        return jsonify({"error": "Job not running"}), 409
    job.cancel_event.set()
    return jsonify({"status": "cancelling"})


@app.get("/file/<job_id>")
@limiter.limit("10/hour")
def serve_file(job_id: str) -> Response:
    with jobs_lock:
        job = jobs.get(job_id)

    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job.status == "running":
        return jsonify({"error": "Download not complete"}), 409
    if job.status == "error":
        return jsonify({"error": job.error or "Download failed"}), 500
    if job.filepath is None or not job.filepath.exists():
        return jsonify({"error": "File no longer available"}), 410

    filepath = job.filepath
    job_dir = DOWNLOADS_DIR / job_id

    def _delete_job() -> None:
        shutil.rmtree(job_dir, ignore_errors=True)
        with jobs_lock:
            jobs.pop(job_id, None)
        logger.info("Deleted temp files for job %s", job_id)

    timer = threading.Timer(5, _delete_job)
    timer.daemon = True
    timer.start()

    return send_file(filepath, as_attachment=True, download_name=filepath.name)


if __name__ == "__main__":
    app.run(debug=True)
