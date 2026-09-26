"""Weekly cycle logic.

Every submission belongs to a "cycle", named by the Thursday-noon deadline it counts toward.
A link sent Thursday at 12:01 PM rolls into next week's cycle automatically.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from config import Config


def tz():
    return ZoneInfo(Config.TIMEZONE)


def now():
    return datetime.now(tz())


def _deadline_on(d):
    return datetime.combine(d, time(Config.DEADLINE_HOUR, 0), tzinfo=tz())


def next_deadline(dt=None):
    """The first deadline strictly after dt."""
    local = (dt or now()).astimezone(tz())
    days = (Config.DEADLINE_WEEKDAY - local.weekday()) % 7
    candidate = _deadline_on(local.date() + timedelta(days=days))
    if local >= candidate:
        candidate = _deadline_on(candidate.date() + timedelta(days=7))
    return candidate


def open_cycle(dt=None):
    """Cycle that new submissions go into right now."""
    return next_deadline(dt).date().isoformat()


def last_closed_deadline(dt=None):
    return _deadline_on(next_deadline(dt).date() - timedelta(days=7))


def last_closed_cycle(dt=None):
    return last_closed_deadline(dt).date().isoformat()


def deadline_of(cycle_id):
    return _deadline_on(date.fromisoformat(cycle_id))


def label(cycle_id):
    dt = deadline_of(cycle_id)
    clock = dt.strftime("%I:%M %p").lstrip("0")
    return f"{dt:%A, %B} {dt.day} at {clock} {dt.tzname()}"


def short_label(cycle_id):
    dt = deadline_of(cycle_id)
    return f"{dt:%a, %b} {dt.day}, {dt.year}"


def in_reminder_window(dt=None):
    """Monday from the reminder hour, plus Tuesday as a catch-up if the server was asleep."""
    local = (dt or now()).astimezone(tz())
    return (local.weekday() == 0 and local.hour >= Config.REMINDER_HOUR) or local.weekday() == 1
