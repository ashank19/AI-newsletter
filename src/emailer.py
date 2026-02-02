import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List


def _split_recipients(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def send_email(subject: str, text_body: str, html_body: str) -> None:
    host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    port = int(os.getenv("EMAIL_PORT", "587"))
    user = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_APP_PASSWORD")
    sender = os.getenv("EMAIL_FROM", user)
    recipients = _split_recipients(os.getenv("EMAIL_TO", ""))

    if not user or not password or not sender or not recipients:
        raise ValueError("Email configuration is incomplete. Check EMAIL_* values in .env")

    # Gmail app passwords are often shown with spaces; strip them for login.
    password = password.replace(" ", "")

    if sender == "your_gmail@gmail.com":
        sender = user

    message = MIMEMultipart("alternative")
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject

    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(sender, recipients, message.as_string())
