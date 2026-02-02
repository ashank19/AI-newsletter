import os
from dotenv import load_dotenv

from newsletter import load_config, build_sections, render_html, render_text
from emailer import send_email


def main() -> None:
    load_dotenv()
    config = load_config(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    sections = build_sections(config)
    subject = os.getenv("EMAIL_SUBJECT_PREFIX", "[AI Newsletter]") + " Test Run"
    text_body = render_text(sections)
    html_body = render_html(sections)

    # Write a local preview for quick debugging.
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "latest.txt"), "w", encoding="utf-8") as f:
        f.write(text_body)
    with open(os.path.join(output_dir, "latest.html"), "w", encoding="utf-8") as f:
        f.write(html_body)

    send_email(subject, text_body, html_body)


if __name__ == "__main__":
    main()
