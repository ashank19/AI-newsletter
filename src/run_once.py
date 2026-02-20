import os
from dotenv import load_dotenv

from newsletter import load_config, build_sections, render_html, render_text
from emailer import send_email


def main() -> None:
    try:
        load_dotenv()
        print("Loaded .env")
        print("EMAIL_USER:", os.getenv("EMAIL_USER"))
        print("EMAIL_TO:", os.getenv("EMAIL_TO"))
        print("EMAIL_HOST:", os.getenv("EMAIL_HOST"))
        config = load_config(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
        print("Loaded config.yaml")
        sections = build_sections(config)
        print("Built sections")
        subject = "Daily newsletter"
        text_body = render_text(sections)
        html_body = render_html(sections)
        print("Rendered email content")

        # Write a local preview for quick debugging.
        output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "latest.txt"), "w", encoding="utf-8") as f:
            f.write(text_body)
        with open(os.path.join(output_dir, "latest.html"), "w", encoding="utf-8") as f:
            f.write(html_body)
        print("Wrote output previews")

        send_email(subject, text_body, html_body)
        print("Email sent")
    except Exception as exc:
        import traceback
        print("Run failed:", exc)
        traceback.print_exc()


if __name__ == "__main__":
    main()
