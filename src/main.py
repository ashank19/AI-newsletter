import os
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from newsletter import load_config, build_sections, render_html, render_text
from emailer import send_email
from cleanup import cleanup_audio_artifacts


def run_digest() -> None:
    try:
        config = load_config(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
        sections = build_sections(config)

        subject = "Daily newsletter"

        text_body = render_text(sections)
        html_body = render_html(sections)

        output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "latest.txt"), "w", encoding="utf-8") as f:
            f.write(text_body)
        with open(os.path.join(output_dir, "latest.html"), "w", encoding="utf-8") as f:
            f.write(html_body)

        send_email(subject, text_body, html_body)
    finally:
        cleanup_audio_artifacts()


def main() -> None:
    load_dotenv()

    timezone = os.getenv("TIMEZONE", "America/New_York")
    hour = int(os.getenv("SEND_HOUR", "6"))
    minute = int(os.getenv("SEND_MINUTE", "0"))

    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(run_digest, CronTrigger(hour=hour, minute=minute))

    print(f"Scheduler running: daily at {hour:02d}:{minute:02d} ({timezone})")
    scheduler.start()


if __name__ == "__main__":
    main()
