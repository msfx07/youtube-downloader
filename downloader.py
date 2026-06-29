#!/usr/bin/env python3
"""YouTube downloader using yt-dlp. Saves video to /downloads inside container."""

import sys
import logging
import os
from pathlib import Path
from dataclasses import dataclass
import argparse
import yt_dlp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class DownloadConfig:
    resolution: str = "best"
    format: str = "mp4"
    audio_only: str | None = None


def parse_args() -> tuple[str, DownloadConfig, bool]:
    parser = argparse.ArgumentParser(
        description="Download YouTube videos using yt-dlp.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("url", help="YouTube URL to download")
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="List available streams for the URL and exit",
    )
    parser.add_argument(
        "--resolution",
        choices=["best", "1080p", "720p", "480p"],
        default="best",
        help="Video resolution (default: best)",
    )
    parser.add_argument(
        "--format",
        choices=["mp4", "mkv", "webm"],
        default=None,
        dest="output_format",
        help="Output container format (default: mp4)",
    )
    parser.add_argument(
        "--audio-only",
        choices=["mp3", "m4a", "opus"],
        default=None,
        help="Download audio only in specified format",
    )

    args = parser.parse_args()

    if args.audio_only is not None:
        if args.resolution != "best":
            parser.error("--audio-only cannot be combined with --resolution")
        if args.output_format is not None:
            parser.error("--audio-only cannot be combined with --format")

    # Apply default after exclusion check
    if args.output_format is None:
        args.output_format = "mp4"

    config = DownloadConfig(
        resolution=args.resolution,
        format=args.output_format,
        audio_only=args.audio_only,
    )
    return args.url, config, args.list_formats


OUTPUT_DIR = Path("/downloads")


def _build_format_selector(config: DownloadConfig) -> str:
    if config.audio_only == "mp3":
        return "bestaudio/best"
    if config.audio_only == "m4a":
        return "bestaudio[ext=m4a]/bestaudio/best"
    if config.audio_only == "opus":
        return "bestaudio[ext=webm]/bestaudio/best"

    height = config.resolution.rstrip("p")  # "1080p" → "1080", "best" → "best"
    res = f"[height<={height}]" if config.resolution != "best" else ""

    if config.format == "webm":
        return f"bestvideo{res}[ext=webm]+bestaudio[ext=webm]/best"
    return f"bestvideo{res}+bestaudio/best"


def build_options(output_dir: Path, config: DownloadConfig) -> dict:
    opts: dict = {
        "format": _build_format_selector(config),
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "logger": logger,
        "progress_hooks": [_progress_hook],
    }

    if config.audio_only == "mp3":
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
        ]
    elif config.audio_only == "m4a":
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}
        ]
    elif config.audio_only == "opus":
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "opus"}
        ]
    elif config.audio_only is None:
        opts["merge_output_format"] = config.format
        opts["postprocessors"] = [
            {"key": "FFmpegVideoConvertor", "preferedformat": config.format}
        ]

    return opts


def _progress_hook(d: dict) -> None:
    if d["status"] == "finished":
        logger.info("Download complete: %s", d.get("filename", "unknown"))
    elif d["status"] == "error":
        logger.error("Download error: %s", d.get("filename", "unknown"))


def download(url: str, config: DownloadConfig) -> None:
    if not OUTPUT_DIR.exists():
        logger.error("Output dir %s does not exist. Mount a volume to /downloads.", OUTPUT_DIR)
        sys.exit(1)

    os.umask(0o002)

    opts = build_options(OUTPUT_DIR, config)
    logger.info("Downloading: %s", url)
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            logger.error("Download failed: %s", e)
            sys.exit(1)


def list_formats(url: str) -> None:
    opts = {
        "listformats": True,
        "skip_download": True,
        "logger": logger,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            logger.error("Failed to list formats: %s", e)
            sys.exit(1)


def main() -> None:
    url, config, list_fmt = parse_args()

    if list_fmt:
        list_formats(url)
        return

    download(url, config)


if __name__ == "__main__":
    main()
