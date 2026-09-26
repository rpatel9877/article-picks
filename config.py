"""App configuration. Everything here comes from environment variables (or a .env file),
so nothing secret ever lives in the code."""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # Branding and access
    FIRM_NAME = os.getenv("FIRM_NAME", "Investment Team")
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
    TEAM_ACCESS_CODE = os.getenv("TEAM_ACCESS_CODE", "")  # optional shared code on the form
    APP_URL = os.getenv("APP_URL", "http://localhost:5000").rstrip("/")

    # Schedule (Monday reminder, Thursday noon deadline)
    TIMEZONE = os.getenv("TIMEZONE", "America/Chicago")
    REMINDER_HOUR = int(os.getenv("REMINDER_HOUR", "9"))
    DEADLINE_WEEKDAY = 3  # Monday=0 ... Thursday=3
    DEADLINE_HOUR = int(os.getenv("DEADLINE_HOUR", "12"))

    # Storage
    DATA_DIR = os.getenv("DATA_DIR", "data")
    DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(DATA_DIR, "digest.db"))
    OUTPUT_DIR = os.path.join(DATA_DIR, "reports")
    OUTBOX_DIR = os.path.join(DATA_DIR, "outbox")

    # AI scoring (optional: the app falls back to basic rules without a key)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    # Email (works with Microsoft 365, Gmail, or any SMTP provider)
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")

    # Background jobs
    ENABLE_SCHEDULER = _bool("ENABLE_SCHEDULER", True)
    CRON_KEY = os.getenv("CRON_KEY", "")  # lets an outside service trigger /tasks/tick
