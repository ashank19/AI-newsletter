# Daily Newsletter

A small, personal project that sends a **daily AI updates + news digest** to your email. It pulls the most recent AI‑related items (e.g., Hacker News) and summarizes them into concise bullet points so you can scan the latest developments quickly.

## What it does
- Fetches the latest AI‑related stories
- Includes relevant news updates when available
- Summarizes each item into short bullet points
- Sends a clean daily email digest

## Quick start

1) Create `.env` from the example:
```
cp .env.example .env
```

2) Fill in your email settings in `.env`.

3) Install dependencies (recommended: inside a virtualenv):
```
pip install -r requirements.txt
```

4) Make sure Ollama is running (used for summarization by default):

- Install Ollama (macOS app), then in a terminal:
```
ollama serve
```

- Pull the model you configured in `.env` (example):
```
ollama pull llama3.1:8b
```

4) Test a one‑off send:
```
python src/run_once.py
```

## Debug: verify latest YouTube URLs

This prints the latest video URL per configured channel (for debugging only):
```
python src/debug_youtube_latest.py
```

This prints the generated summaries for the latest videos (for debugging only):
```
python src/debug_youtube_summaries.py
```

## Transcripts for videos without captions (free, local)

If a YouTube video has no transcript/captions available, the project can still summarize it **if you provide an audio file** for that video ID.

1) Install ffmpeg:
```
brew install ffmpeg
```

2) If you enable the optional audio fetcher, you also need `yt-dlp`:
```
brew install yt-dlp
```

2) Transcription engine (default is `faster_whisper`).
Default model is `small` (set `WHISPER_MODEL` if you want a different one).

3) Put the audio file here (any of these extensions: `.m4a`, `.mp3`, `.wav`, `.aac`, `.opus`, `.webm`):
```
AI-newsletter/.cache/audio/<video_id>.m4a
```

4) The next run will:
- normalize audio to 16kHz mono wav
- transcribe + translate to English using local Whisper (faster-whisper)
- summarize using your local Ollama model (make sure `ollama serve` is running)

Optional automation hook:
- There is a stub module at `AI-newsletter/src/audio_fetcher.py`.
- If you implement `fetch_audio_for_video(...)` yourself (only for content you own/have permission to process),
  and set `ENABLE_AUDIO_FETCHER=true` in `.env`, the pipeline will call it when captions are missing.

## Cron setup (macOS)

Run daily at 6:00 AM local time:

```
crontab -e
```
Add this line:
```
0 6 * * * /bin/bash -lc 'cd "/Users/arnavsmac/Downloads/University_at_Buffalo/Personal/AI-newsletter" && "./.venv/bin/python" "src/run_once.py" >> "./cron.log" 2>&1'
```

## CrewAI mode (OpenAI)

To enable CrewAI summarization, set in `.env`:
```
USE_CREWAI=true
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL_NAME=gpt-4o
```

## Docker (optional)

If you prefer Docker:
```
docker compose build
docker compose run --rm ai-newsletter
```

## Gmail App Password

If you use Gmail SMTP, create an App Password:
- Enable 2‑Step Verification
- Go to **Security → App passwords**
- Create an app password for **Mail**
- Put it into `EMAIL_APP_PASSWORD` in `.env`

## Notes
- `.env` is ignored by git and should never be committed.
- This project is for **personal use** and **daily AI updates**.
