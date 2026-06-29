import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from downloader import DownloadConfig, _build_format_selector, build_options, parse_args, list_formats


def test_download_config_defaults():
    config = DownloadConfig()
    assert config.resolution == "best"
    assert config.format == "mp4"
    assert config.audio_only is None


def test_download_config_custom_values():
    config = DownloadConfig(resolution="1080p", format="mkv", audio_only="mp3")
    assert config.resolution == "1080p"
    assert config.format == "mkv"
    assert config.audio_only == "mp3"


# --- _build_format_selector ---

def test_format_selector_default():
    assert _build_format_selector(DownloadConfig()) == "bestvideo+bestaudio/best"


def test_format_selector_1080p_mp4():
    config = DownloadConfig(resolution="1080p", format="mp4")
    assert _build_format_selector(config) == "bestvideo[height<=1080]+bestaudio/best"


def test_format_selector_720p_webm():
    config = DownloadConfig(resolution="720p", format="webm")
    assert _build_format_selector(config) == "bestvideo[height<=720][ext=webm]+bestaudio[ext=webm]/best"


def test_format_selector_480p_mkv():
    config = DownloadConfig(resolution="480p", format="mkv")
    assert _build_format_selector(config) == "bestvideo[height<=480]+bestaudio/best"


def test_format_selector_audio_mp3():
    assert _build_format_selector(DownloadConfig(audio_only="mp3")) == "bestaudio/best"


def test_format_selector_audio_m4a():
    assert _build_format_selector(DownloadConfig(audio_only="m4a")) == "bestaudio[ext=m4a]/bestaudio/best"


def test_format_selector_audio_opus():
    assert _build_format_selector(DownloadConfig(audio_only="opus")) == "bestaudio[ext=webm]/bestaudio/best"


# --- build_options ---

def test_build_options_default_format_and_merge():
    opts = build_options(Path("/downloads"), DownloadConfig())
    assert opts["format"] == "bestvideo+bestaudio/best"
    assert opts["merge_output_format"] == "mp4"
    assert any(p["key"] == "FFmpegVideoConvertor" for p in opts["postprocessors"])


def test_build_options_mkv_merge():
    opts = build_options(Path("/downloads"), DownloadConfig(format="mkv"))
    assert opts["merge_output_format"] == "mkv"
    assert any(p["preferedformat"] == "mkv" for p in opts["postprocessors"])


def test_build_options_audio_mp3_has_extract_postprocessor():
    opts = build_options(Path("/downloads"), DownloadConfig(audio_only="mp3"))
    assert any(p["key"] == "FFmpegExtractAudio" and p["preferredcodec"] == "mp3"
               for p in opts["postprocessors"])
    assert "merge_output_format" not in opts


def test_build_options_audio_m4a_has_extract_postprocessor():
    opts = build_options(Path("/downloads"), DownloadConfig(audio_only="m4a"))
    assert any(p["key"] == "FFmpegExtractAudio" and p["preferredcodec"] == "m4a"
               for p in opts["postprocessors"])
    assert "merge_output_format" not in opts


def test_build_options_audio_opus_has_extract_postprocessor():
    opts = build_options(Path("/downloads"), DownloadConfig(audio_only="opus"))
    assert any(p["key"] == "FFmpegExtractAudio" and p["preferredcodec"] == "opus"
               for p in opts["postprocessors"])
    assert "merge_output_format" not in opts


def test_build_options_outtmpl_uses_output_dir():
    opts = build_options(Path("/custom"), DownloadConfig())
    assert opts["outtmpl"].startswith("/custom/")


# --- parse_args ---

def test_parse_args_url_only(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "https://example.com"])
    url, config, list_fmt = parse_args()
    assert url == "https://example.com"
    assert config.resolution == "best"
    assert config.format == "mp4"
    assert config.audio_only is None
    assert list_fmt is False


def test_parse_args_resolution_flag(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "URL", "--resolution", "1080p"])
    _, config, _ = parse_args()
    assert config.resolution == "1080p"


def test_parse_args_format_flag(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "URL", "--format", "webm"])
    _, config, _ = parse_args()
    assert config.format == "webm"


def test_parse_args_audio_only_mp3(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "URL", "--audio-only", "mp3"])
    _, config, _ = parse_args()
    assert config.audio_only == "mp3"


def test_parse_args_list_formats_flag(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "URL", "--list-formats"])
    _, _, list_fmt = parse_args()
    assert list_fmt is True


def test_parse_args_audio_only_rejects_resolution(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "URL", "--audio-only", "mp3", "--resolution", "1080p"])
    with pytest.raises(SystemExit) as exc:
        parse_args()
    assert exc.value.code == 2


def test_parse_args_audio_only_rejects_format(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "URL", "--audio-only", "mp3", "--format", "webm"])
    with pytest.raises(SystemExit) as exc:
        parse_args()
    assert exc.value.code == 2


def test_parse_args_audio_only_rejects_format_mp4(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "URL", "--audio-only", "mp3", "--format", "mp4"])
    with pytest.raises(SystemExit) as exc:
        parse_args()
    assert exc.value.code == 2


def test_parse_args_invalid_resolution_rejected(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "URL", "--resolution", "4k"])
    with pytest.raises(SystemExit) as exc:
        parse_args()
    assert exc.value.code == 2


def test_parse_args_invalid_format_rejected(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py", "URL", "--format", "avi"])
    with pytest.raises(SystemExit) as exc:
        parse_args()
    assert exc.value.code == 2


def test_parse_args_no_url_exits(monkeypatch):
    monkeypatch.setattr("sys.argv", ["downloader.py"])
    with pytest.raises(SystemExit) as exc:
        parse_args()
    assert exc.value.code == 2


# --- list_formats ---

def test_list_formats_calls_extract_info_with_download_false(monkeypatch):
    mock_ydl_instance = MagicMock()
    mock_ydl_class = MagicMock(return_value=mock_ydl_instance)
    mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
    mock_ydl_instance.__exit__ = MagicMock(return_value=False)

    with patch("yt_dlp.YoutubeDL", mock_ydl_class):
        list_formats("https://example.com")

    call_opts = mock_ydl_class.call_args[0][0]
    assert call_opts["listformats"] is True
    assert call_opts.get("skip_download") is True or call_opts.get("simulate") is True

    mock_ydl_instance.extract_info.assert_called_once_with(
        "https://example.com", download=False
    )


def test_list_formats_exits_1_on_download_error(monkeypatch):
    import yt_dlp.utils

    mock_ydl_instance = MagicMock()
    mock_ydl_class = MagicMock(return_value=mock_ydl_instance)
    mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
    mock_ydl_instance.__exit__ = MagicMock(return_value=False)
    mock_ydl_instance.extract_info.side_effect = yt_dlp.utils.DownloadError("not found")

    with patch("yt_dlp.YoutubeDL", mock_ydl_class):
        with pytest.raises(SystemExit) as exc:
            list_formats("https://example.com")
    assert exc.value.code == 1
