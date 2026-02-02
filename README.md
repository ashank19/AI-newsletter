# AI Newsletter

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

3) Install dependencies:
```
pip install -r requirements.txt
```

4) Test a one‑off send:
```
python src/run_once.py
```

## Cron setup (macOS)

Run daily at 6:00 AM local time:

```
crontab -e
```
Add this line:
```
0 6 * * * /bin/bash -lc 'cd "/Users/arnavsmac/Downloads/University_at_Buffalo/Personal/AI-newsletter" && source .venv/bin/activate && python src/run_once.py'
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
