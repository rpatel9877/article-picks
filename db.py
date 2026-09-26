"""SQLite storage: submissions, cached article analyses, editable settings, and job history."""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle TEXT NOT NULL,
    submitter TEXT NOT NULL,
    url TEXT NOT NULL,
    note TEXT DEFAULT '',
    submitted_at TEXT NOT NULL,
    UNIQUE (cycle, submitter, url)
);
CREATE INDEX IF NOT EXISTS idx_submissions_cycle ON submissions (cycle);
CREATE TABLE IF NOT EXISTS analyses (
    cache_key TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    data TEXT NOT NULL,
    analyzed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_url ON analyses (url);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS job_runs (
    job TEXT NOT NULL,
    cycle TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT DEFAULT '',
    PRIMARY KEY (job, cycle)
);
"""

DEFAULT_WORLDVIEW = """Replace this with a few sentences in your own words. For example:
- How we invest (time horizon, style, what we emphasize and avoid)
- Our current view of markets and the economy
- Themes we want clients to understand better
- Tone we want: calm, evidence-based, skeptical of hype and short-term forecasts"""

DEFAULT_SETTINGS = {
    "team_members": "Jane Smith, jane@yourfirm.com\nJohn Doe, john@yourfirm.com",
    "report_recipients": "",
    "reminder_cc": "",
    "worldview": DEFAULT_WORLDVIEW,
    "past_examples": "",
    "extra_paywall_domains": "",
    "reminders_enabled": "1",
    "reports_enabled": "1",
}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    folder = os.path.dirname(Config.DATABASE_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


# ---------- settings ----------
def get_settings():
    with connect() as c:
        rows = c.execute("SELECT key, value FROM settings").fetchall()
    settings = dict(DEFAULT_SETTINGS)
    settings.update({r["key"]: r["value"] for r in rows})
    return settings


def save_settings(values):
    with connect() as c:
        for key, value in values.items():
            if key in DEFAULT_SETTINGS:
                c.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )


def parse_team(text):
    """Each line: 'Name' or 'Name, email' or 'Name <email>'."""
    people = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(.*?)\s*<([^>]+)>\s*$", line)
        if match:
            name, email = match.group(1), match.group(2)
        elif "," in line:
            name, email = (p.strip() for p in line.split(",", 1))
        else:
            name, email = line, ""
        name = name.strip().strip('"')
        email = email.strip() if "@" in email else ""
        if name and name not in [p["name"] for p in people]:
            people.append({"name": name, "email": email})
    return people


def parse_emails(text):
    return re.findall(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+", text or "")


# ---------- submissions ----------
def add_submission(cycle, submitter, url, note=""):
    """Returns False if this person already sent this link this week."""
    with connect() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO submissions (cycle, submitter, url, note, submitted_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cycle, submitter, url, note, utcnow()),
        )
        return cur.rowcount == 1


def list_submissions(cycle):
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM submissions WHERE cycle = ? ORDER BY submitted_at, id", (cycle,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_submission(sub_id):
    with connect() as c:
        c.execute("DELETE FROM submissions WHERE id = ?", (sub_id,))


def list_cycles():
    with connect() as c:
        rows = c.execute("SELECT DISTINCT cycle FROM submissions ORDER BY cycle DESC").fetchall()
    return [r["cycle"] for r in rows]


# ---------- analysis cache ----------
def get_analysis(cache_key):
    with connect() as c:
        row = c.execute("SELECT data FROM analyses WHERE cache_key = ?", (cache_key,)).fetchone()
    return json.loads(row["data"]) if row else None


def save_analysis(cache_key, url, data):
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO analyses (cache_key, url, data, analyzed_at) VALUES (?, ?, ?, ?)",
            (cache_key, url, json.dumps(data), utcnow()),
        )


def clear_analyses(urls):
    with connect() as c:
        c.executemany("DELETE FROM analyses WHERE url = ?", [(u,) for u in urls])


# ---------- job history (also acts as a lock so nothing is sent twice) ----------
def claim_job(job, cycle):
    with connect() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO job_runs (job, cycle, ran_at, status) VALUES (?, ?, ?, 'running')",
            (job, cycle, utcnow()),
        )
        return cur.rowcount == 1


def record_job(job, cycle, status, detail=""):
    with connect() as c:
        c.execute(
            "INSERT INTO job_runs (job, cycle, ran_at, status, detail) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(job, cycle) DO UPDATE SET ran_at = excluded.ran_at, "
            "status = excluded.status, detail = excluded.detail",
            (job, cycle, utcnow(), status, detail),
        )


def recent_runs(limit=8):
    with connect() as c:
        rows = c.execute("SELECT * FROM job_runs ORDER BY ran_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
