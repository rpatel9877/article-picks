"""Sends email through any SMTP provider (Microsoft 365, Gmail, SendGrid, etc.).
If email isn't configured yet, messages are saved to data/outbox so nothing is lost."""
import os
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage

from config import Config

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _save_to_outbox(msg):
    os.makedirs(Config.OUTBOX_DIR, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", (msg["Subject"] or "message").lower()).strip("-")[:50]
    path = os.path.join(Config.OUTBOX_DIR, f"{datetime.now():%Y%m%d-%H%M%S}-{slug}.eml")
    with open(path, "wb") as fh:
        fh.write(bytes(msg))
    return path


def send_email(to, subject, text, html=None, attachments=(), cc=()):
    """Returns (sent: bool, message: str)."""
    to, cc = [a for a in to if a], [a for a in cc if a]
    if not to:
        return False, "No recipients are set. Add them on the Settings page."

    msg = EmailMessage()
    msg["From"] = Config.SMTP_FROM or Config.SMTP_USER or "article-picks@localhost"
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    for filename, data, mime in attachments:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    if not Config.SMTP_HOST:
        path = _save_to_outbox(msg)
        return False, f"Email isn't set up yet, so the message was saved to {path}."

    try:
        context = ssl.create_default_context()
        if Config.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT, context=context, timeout=30)
        else:
            server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=30)
            server.starttls(context=context)
        with server:
            if Config.SMTP_USER:
                server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            server.send_message(msg)
        return True, f"Sent to {', '.join(to + cc)}."
    except Exception as exc:
        path = _save_to_outbox(msg)
        return False, f"Sending failed ({exc}). A copy was saved to {path}."
