import os
from pathlib import Path


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def cleanup_audio_artifacts() -> None:
    """
    Delete cached YouTube audio + normalized wav artifacts after a run.

    This keeps disk usage low and matches the "don't persist audio" preference.
    """
    if not _truthy(os.getenv("CLEANUP_AUDIO_CACHE_AFTER_RUN", "true")):
        return

    project_root = Path(__file__).resolve().parent.parent

    audio_dir = Path(os.getenv("AUDIO_CACHE_DIR", str(project_root / ".cache" / "audio"))).expanduser()
    normalized_dir = project_root / ".cache" / "normalized"

    for d in (audio_dir, normalized_dir):
        if not d.exists() or not d.is_dir():
            continue
        for p in d.iterdir():
            # Only delete regular files (leave directories alone).
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass

