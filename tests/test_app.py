import threading
import time
from pathlib import Path
from queue import Queue
from queue import Queue as StdQueue
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from app import app as flask_app, JobState, jobs, jobs_lock, _validate_request
from app import _progress_hook, _run_download, DOWNLOADS_DIR, _strip_playlist_params
from downloader import DownloadConfig


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["RATELIMIT_ENABLED"] = False
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clear_jobs():
    with jobs_lock:
        jobs.clear()
    yield
    with jobs_lock:
        jobs.clear()


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"YouTube Downloader" in resp.data


def test_index_contains_required_elements(client):
    resp = client.get("/")
    body = resp.data.decode()
    assert "YouTube Downloader" in body
    assert 'id="url"' in body
    assert 'id="resolution"' in body
    assert 'id="format"' in body
    assert 'id="audioOnly"' in body
    assert 'id="dlBtn"' in body
    assert 'id="progressSection"' in body
    assert 'id="saveBtn"' in body
    assert "index.js" in body    # JS bundle referenced
    js = client.get("/static/index.js").data.decode()
    assert "/download" in js     # fetch target
    assert "/stream/" in js      # EventSource target
    assert "/file/" in js        # save file target


def test_jobstate_defaults():
    q = Queue()
    job = JobState(status="running", queue=q)
    assert job.status == "running"
    assert job.filepath is None
    assert job.error is None
    assert job.created_at > 0


def test_validate_valid_youtube_url():
    url, config = _validate_request({"url": "https://www.youtube.com/watch?v=abc"})
    assert url == "https://www.youtube.com/watch?v=abc"
    assert isinstance(config, DownloadConfig)


def test_validate_valid_youtu_be_url():
    url, config = _validate_request({"url": "https://youtu.be/abc"})
    assert url is not None


def test_validate_rejects_non_youtube():
    result = _validate_request({"url": "https://vimeo.com/123"})
    assert result[0] is None
    assert "YouTube" in result[1]


def test_validate_rejects_http():
    result = _validate_request({"url": "http://youtube.com/watch?v=abc"})
    assert result[0] is None


def test_validate_invalid_resolution():
    result = _validate_request({"url": "https://youtube.com/watch?v=abc", "resolution": "4k"})
    assert result[0] is None
    assert "resolution" in result[1]


def test_validate_invalid_format():
    result = _validate_request({"url": "https://youtube.com/watch?v=abc", "format": "avi"})
    assert result[0] is None
    assert "format" in result[1]


def test_validate_invalid_audio_only():
    result = _validate_request({"url": "https://youtube.com/watch?v=abc", "audio_only": "wav"})
    assert result[0] is None
    assert "audio_only" in result[1]


def test_validate_audio_only_with_resolution():
    result = _validate_request({
        "url": "https://youtube.com/watch?v=abc",
        "audio_only": "mp3",
        "resolution": "1080p",
    })
    assert result[0] is None
    assert "resolution" in result[1]


def test_validate_audio_only_with_format():
    result = _validate_request({
        "url": "https://youtube.com/watch?v=abc",
        "audio_only": "mp3",
        "format": "mkv",
    })
    assert result[0] is None
    assert "format" in result[1]


def test_validate_defaults():
    url, config = _validate_request({"url": "https://youtu.be/abc"})
    assert config.resolution == "best"
    assert config.format == "mp4"
    assert config.audio_only is None


def test_post_download_returns_job_id(client):
    with patch("app._run_download"):
        resp = client.post("/download", json={
            "url": "https://www.youtube.com/watch?v=abc",
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # UUID length


def test_post_download_invalid_url_returns_400(client):
    resp = client.post("/download", json={"url": "https://vimeo.com/123"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_post_download_invalid_resolution_returns_400(client):
    resp = client.post("/download", json={
        "url": "https://youtube.com/watch?v=abc",
        "resolution": "4k",
    })
    assert resp.status_code == 400


def test_post_download_creates_job_in_store(client):
    with patch("app._run_download"):
        resp = client.post("/download", json={
            "url": "https://www.youtube.com/watch?v=abc",
        })
    job_id = resp.get_json()["job_id"]
    with jobs_lock:
        assert job_id in jobs
        assert jobs[job_id].status == "running"


def test_progress_hook_pushes_progress_event():
    q = StdQueue()
    job = JobState(status="running", queue=q)
    _progress_hook(
        {"status": "downloading", "_percent_str": " 45.0%", "_speed_str": "1.2MiB/s", "eta": 10},
        job,
    )
    event = q.get_nowait()
    assert event["type"] == "progress"
    assert event["percent"] == 45.0
    assert event["speed"] == "1.2MiB/s"
    assert event["eta"] == 10


def test_progress_hook_ignores_non_downloading_status():
    q = StdQueue()
    job = JobState(status="running", queue=q)
    _progress_hook({"status": "finished", "filename": "test.mp4"}, job)
    assert q.empty()


def test_jobstate_has_cancel_event():
    q = Queue()
    job = JobState(status="running", queue=q)
    assert hasattr(job, "cancel_event")
    assert isinstance(job.cancel_event, threading.Event)
    assert not job.cancel_event.is_set()


def test_cancel_unknown_job_returns_404(client):
    resp = client.delete("/cancel/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_cancel_running_job_returns_200(client):
    job_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with jobs_lock:
        jobs[job_id] = JobState(status="running", queue=StdQueue())
    resp = client.delete(f"/cancel/{job_id}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cancelling"


def test_cancel_sets_cancel_event(client):
    job_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    with jobs_lock:
        jobs[job_id] = JobState(status="running", queue=StdQueue())
    client.delete(f"/cancel/{job_id}")
    with jobs_lock:
        assert jobs[job_id].cancel_event.is_set()


def test_cancel_finished_job_returns_409(client):
    job_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    with jobs_lock:
        jobs[job_id] = JobState(status="finished", queue=StdQueue())
    resp = client.delete(f"/cancel/{job_id}")
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_progress_hook_raises_cancelled_when_event_set():
    q = StdQueue()
    job = JobState(status="running", queue=q)
    job.cancel_event.set()
    with pytest.raises(yt_dlp.utils.DownloadCancelled):
        _progress_hook(
            {"status": "downloading", "_percent_str": "50.0%", "_speed_str": "1MiB/s", "eta": 5},
            job,
        )


def test_run_download_cancelled_pushes_cancelled_event(tmp_path, monkeypatch):
    monkeypatch.setattr("app.DOWNLOADS_DIR", tmp_path)
    job_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    q = StdQueue()
    job_obj = JobState(status="running", queue=q)
    with jobs_lock:
        jobs[job_id] = job_obj

    mock_ydl_instance = MagicMock()
    mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
    mock_ydl_instance.__exit__ = MagicMock(return_value=False)
    mock_ydl_instance.download.side_effect = yt_dlp.utils.DownloadCancelled("cancelled")

    with patch("app.yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
        _run_download(job_id, "https://youtube.com/watch?v=test", DownloadConfig())

    with jobs_lock:
        assert jobs[job_id].status == "cancelled"

    event = q.get_nowait()
    assert event["type"] == "cancelled"


def test_run_download_success_pushes_finished(tmp_path, monkeypatch):
    monkeypatch.setattr("app.DOWNLOADS_DIR", tmp_path)

    job_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    q = StdQueue()
    with jobs_lock:
        jobs[job_id] = JobState(status="running", queue=q)

    fake_filepath = tmp_path / job_id / "My Video.mp4"

    def fake_download(urls):
        fake_filepath.parent.mkdir(parents=True, exist_ok=True)
        fake_filepath.write_bytes(b"fake")

    mock_ydl_instance = MagicMock()
    mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
    mock_ydl_instance.__exit__ = MagicMock(return_value=False)
    mock_ydl_instance.download.side_effect = fake_download

    with patch("app.yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
        _run_download(job_id, "https://youtube.com/watch?v=test", DownloadConfig())

    assert jobs[job_id].status == "finished"
    assert jobs[job_id].filepath == fake_filepath

    event = q.get_nowait()
    assert event["type"] == "finished"
    assert event["filename"] == "My Video.mp4"


def test_run_download_error_pushes_error_event(tmp_path, monkeypatch):
    monkeypatch.setattr("app.DOWNLOADS_DIR", tmp_path)

    job_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    q = StdQueue()
    with jobs_lock:
        jobs[job_id] = JobState(status="running", queue=q)

    mock_ydl_instance = MagicMock()
    mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
    mock_ydl_instance.__exit__ = MagicMock(return_value=False)
    mock_ydl_instance.download.side_effect = yt_dlp.utils.DownloadError("Video unavailable")

    with patch("app.yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
        _run_download(job_id, "https://youtube.com/watch?v=bad", DownloadConfig())

    assert jobs[job_id].status == "error"

    event = q.get_nowait()
    assert event["type"] == "error"
    assert "Download failed" in event["message"]


def test_stream_unknown_job_returns_404(client):
    resp = client.get("/stream/00000000-0000-0000-0000-000000000002")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_stream_known_job_returns_event_stream_content_type(client):
    job_id = "11111111-1111-1111-1111-111111111111"
    q = StdQueue()
    q.put({"type": "finished", "filename": "test.mp4"})
    with jobs_lock:
        jobs[job_id] = JobState(status="finished", queue=q)

    resp = client.get(f"/stream/{job_id}")
    assert "text/event-stream" in resp.content_type


def test_stream_yields_finished_event(client):
    job_id = "22222222-2222-2222-2222-222222222222"
    q = StdQueue()
    q.put({"type": "finished", "filename": "video.mp4"})
    with jobs_lock:
        jobs[job_id] = JobState(status="finished", queue=q)

    resp = client.get(f"/stream/{job_id}")
    body = b"".join(resp.response)
    assert b'"type": "finished"' in body or b'"type":"finished"' in body
    assert b"video.mp4" in body


def test_file_unknown_job_returns_404(client):
    resp = client.get("/file/00000000-0000-0000-0000-000000000003")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_file_running_job_returns_409(client):
    job_id = "33333333-3333-3333-3333-333333333333"
    with jobs_lock:
        jobs[job_id] = JobState(status="running", queue=StdQueue())
    resp = client.get(f"/file/{job_id}")
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "Download not complete"


def test_file_error_job_returns_500(client):
    job_id = "44444444-4444-4444-4444-444444444444"
    with jobs_lock:
        jobs[job_id] = JobState(status="error", queue=StdQueue(), error="Video unavailable")
    resp = client.get(f"/file/{job_id}")
    assert resp.status_code == 500


def test_file_missing_filepath_returns_410(client):
    job_id = "55555555-5555-5555-5555-555555555555"
    with jobs_lock:
        jobs[job_id] = JobState(status="finished", queue=StdQueue(), filepath=None)
    resp = client.get(f"/file/{job_id}")
    assert resp.status_code == 410
    assert resp.get_json()["error"] == "File no longer available"


def test_file_nonexistent_path_returns_410(client, tmp_path):
    job_id = "66666666-6666-6666-6666-666666666666"
    ghost_path = tmp_path / "gone.mp4"  # file does not exist
    with jobs_lock:
        jobs[job_id] = JobState(status="finished", queue=StdQueue(), filepath=ghost_path)
    resp = client.get(f"/file/{job_id}")
    assert resp.status_code == 410


def test_file_success_serves_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.DOWNLOADS_DIR", tmp_path)
    job_id = "77777777-7777-7777-7777-777777777777"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    test_file = job_dir / "video.mp4"
    test_file.write_bytes(b"fake video content")

    with jobs_lock:
        jobs[job_id] = JobState(status="finished", queue=StdQueue(), filepath=test_file)

    with patch("app.threading.Timer"):  # prevent background deletion during test
        resp = client.get(f"/file/{job_id}")

    assert resp.status_code == 200
    assert resp.data == b"fake video content"


def test_strip_playlist_removes_list_param():
    url = "https://www.youtube.com/watch?v=abc123&list=PLxxx"
    assert _strip_playlist_params(url) == "https://www.youtube.com/watch?v=abc123"


def test_strip_playlist_removes_multiple_playlist_params():
    url = "https://www.youtube.com/watch?v=abc123&list=PLxxx&index=3&start_radio=1"
    assert _strip_playlist_params(url) == "https://www.youtube.com/watch?v=abc123"


def test_strip_playlist_leaves_non_playlist_params():
    url = "https://www.youtube.com/watch?v=abc123&t=30"
    assert _strip_playlist_params(url) == "https://www.youtube.com/watch?v=abc123&t=30"


def test_strip_playlist_no_op_on_clean_url():
    url = "https://www.youtube.com/watch?v=abc123"
    assert _strip_playlist_params(url) == "https://www.youtube.com/watch?v=abc123"


def test_strip_playlist_works_on_youtu_be():
    url = "https://youtu.be/abc123?list=PLxxx&index=1"
    assert _strip_playlist_params(url) == "https://youtu.be/abc123"


def test_validate_strips_playlist_from_submitted_url():
    url, config = _validate_request({
        "url": "https://www.youtube.com/watch?v=abc123&list=PLxxx&index=2"
    })
    assert url == "https://www.youtube.com/watch?v=abc123"


def test_index_inputs_disabled_during_download(client):
    js = client.get("/static/index.js").data.decode()
    assert "setFormLocked" in js
    assert "resolution.disabled" in js
    assert "formatSel.disabled" in js
    assert "audioOnly.disabled" in js


def test_index_contains_cancel_button(client):
    resp = client.get("/")
    body = resp.data.decode()
    assert 'id="cancelBtn"' in body
    js = client.get("/static/index.js").data.decode()
    assert "/cancel/" in js
    assert "cancelled" in js
