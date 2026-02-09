import argparse
import os
import sys

from asr import normalize_audio_to_wav, transcribe_audio_to_english_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug local ASR (ffmpeg normalize -> Whisper translate).")
    parser.add_argument("--input", help="Path to an audio file (m4a/mp3/wav/opus/webm, etc).")
    parser.add_argument("--video-id", help="If set, reads from AUDIO_CACHE_DIR/<video_id>.*")
    args = parser.parse_args()

    audio_path = args.input
    if not audio_path and args.video_id:
        audio_dir = os.getenv("AUDIO_CACHE_DIR", os.path.join(os.path.dirname(__file__), "..", ".cache", "audio"))
        for ext in (".wav", ".m4a", ".mp3", ".aac", ".opus", ".webm"):
            candidate = os.path.join(audio_dir, f"{args.video_id}{ext}")
            if os.path.exists(candidate):
                audio_path = candidate
                break

    if not audio_path:
        print("ERROR: provide --input <audio_path> or --video-id <id>", file=sys.stderr)
        return 2

    audio_path = os.path.abspath(audio_path)
    if not os.path.exists(audio_path):
        print(f"ERROR: file not found: {audio_path}", file=sys.stderr)
        return 2

    normalized_dir = os.path.join(os.path.dirname(__file__), "..", ".cache", "normalized")
    os.makedirs(normalized_dir, exist_ok=True)
    wav_path = os.path.join(normalized_dir, "debug.wav")

    print(f"input={audio_path}")
    print(f"normalized_wav={wav_path}")
    normalize_audio_to_wav(audio_path, wav_path)

    text = transcribe_audio_to_english_text(wav_path)
    print("\n=== TRANSCRIPT (translated to English) ===\n")
    print(text.strip() or "(empty)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

