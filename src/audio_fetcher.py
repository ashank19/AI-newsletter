"""
Audio fetch hook (optional).

This repo does not include an implementation that downloads audio from YouTube.
If you have lawful access to the audio (e.g., your own content / explicit permission),
implement `fetch_audio_for_video` to place an audio file into `output_dir` and return its path.
"""

from __future__ import annotations
import os
import subprocess
from urllib.parse import urlparse, parse_qs
from yt_dlp import YoutubeDL

import os
from typing import Optional


def fetch_audio_for_video(video_url: str, video_id: str, output_dir: str) -> Optional[str]:
    """
    Return a local audio filepath for this video, or None.
    """
    parsed = urlparse(video_url)
    query = parse_qs(parsed.query)

    if "v" not in query:
        raise ValueError("Invalid YouTube URL: missing video ID")

    video_id = query["v"][0]

    os.makedirs(output_dir, exist_ok=True)

    downloaded_path = os.path.join(output_dir, f"{video_id}.%(ext)s")
    wav_audio_path = os.path.join(output_dir, f"{video_id}.wav")

    ydl_opts = {
        # ✅ Explicit, reliable audio formats with fallback
        "format": "140/251/bestaudio",

        "outtmpl": downloaded_path,
        "noplaylist": True,
        "quiet": True,

        # ❌ NO js_runtimes
        # ❌ NO android client
        # ❌ NO PO tokens
        # Let yt-dlp use default web extraction

    }

    # ---- Download ----
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        downloaded_file = ydl.prepare_filename(info)

    # ---- Validate ----
    if not os.path.exists(downloaded_file) or os.path.getsize(downloaded_file) < 1024:
        raise RuntimeError("Audio download failed")

    # ---- Normalize to WAV ----
    ffmpeg_bin = os.getenv("FFMPEG_PATH", "").strip() or "ffmpeg"
    subprocess.run(
        [ffmpeg_bin, "-y", "-i", downloaded_file, "-ar", "16000", "-ac", "1", wav_audio_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )

    return os.path.abspath(wav_audio_path)
    # _ = video_url
    # _ = video_id
    # os.makedirs(output_dir, exist_ok=True)
    # return None
