import os
import subprocess
import wave
from contextlib import closing
from typing import Optional


def _resolve_ffmpeg_path() -> str:
    """
    Resolve ffmpeg binary path.

    Prefer an explicit env var, then common Homebrew locations, then PATH.
    """
    explicit = os.getenv("FFMPEG_PATH", "").strip()
    if explicit:
        return explicit

    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if os.path.exists(candidate):
            return candidate

    return "ffmpeg"


def normalize_audio_to_wav(input_path: str, output_path: str) -> None:
    """
    Normalize audio to 16kHz mono WAV for speech-to-text.
    Requires ffmpeg installed on the system.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        _resolve_ffmpeg_path(),
        "-y",
        "-i",
        input_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-vn",
        output_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({result.returncode}): {result.stderr.strip()}")
    # ffmpeg can "succeed" but still leave an empty/invalid file (e.g., blocked download, zero-length input).
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 4096:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"ffmpeg produced empty output at {output_path!r}. stderr={stderr!r}")
    try:
        with closing(wave.open(output_path, "rb")) as wf:
            if wf.getnframes() <= 0:
                raise RuntimeError(f"normalized wav has 0 frames: {output_path!r}")
    except wave.Error as e:
        raise RuntimeError(f"normalized wav is invalid: {output_path!r} ({e})") from e


def transcribe_audio_to_english_text(wav_path: str) -> str:
    """
    Transcribe (and translate to English) audio using local Whisper.

    Set `ASR_ENGINE`:
    - faster_whisper (default): uses `faster-whisper` (usually faster on CPU)
    - openai_whisper: uses the `openai-whisper` Python package
    """
    # Default to faster-whisper because it's easier to install reliably on macOS.
    engine = os.getenv("ASR_ENGINE", "faster_whisper").strip().lower()
    model_name = os.getenv("WHISPER_MODEL", "small")

    if engine == "openai_whisper":
        import whisper  # from openai-whisper

        model = whisper.load_model(model_name)
        try:
            result = model.transcribe(
                wav_path,
                task="translate",  # translate to English
                fp16=False,        # CPU-safe default
            )
            return (result.get("text") or "").strip()
        except Exception:
            # Treat ASR errors as "no transcript" so upstream can try another video/channel.
            return ""

    # fallback: faster-whisper
    from faster_whisper import WhisperModel

    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    try:
        segments, _info = model.transcribe(wav_path, task="translate", vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments).strip()
    except ValueError:
        # faster-whisper can throw `ValueError: max() arg is an empty sequence` on empty/silent audio.
        return ""
    except Exception:
        return ""


def find_audio_for_video(video_id: str, audio_dir: str) -> Optional[str]:
    if not video_id:
        return None
    for ext in (".m4a", ".mp3", ".wav", ".aac", ".opus", ".webm"):
        candidate = os.path.join(audio_dir, f"{video_id}{ext}")
        if os.path.exists(candidate):
            return candidate
    return None
