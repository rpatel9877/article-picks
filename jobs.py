"""The three automated jobs: Monday reminder, background scoring, and the Thursday report."""
import html
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import cycle as cyc
import db
import mailer
import report
import scorer
from config import Config

log = logging.getLogger("digest.jobs")
_background = ThreadPoolExecutor(max_workers=3, thread_name_prefix="scorer")


# ---------- background scoring (runs right after each submission) ----------
def queue_analysis(urls, refresh=False):
    settings = db.get_settings()
    if refresh:
        db.clear_analyses(urls)
    for url in urls:
        _background.submit(_safe_analyze, url, settings)


def _safe_analyze(url, settings):
    try:
        scorer.analyze(url, settings)
    except Exception:
        log.exception("Scoring failed for %s", url)


# ---------- gathering a week's links ----------
def _group(cycle_id):
    """One entry per unique link, remembering everyone who sent it."""
    grouped = {}
    for s in db.list_submissions(cycle_id):
        entry = grouped.setdefault(s["url"], {"url": s["url"], "submitters": [], "notes": [],
                                              "first_at": s["submitted_at"], "ids": []})
        entry["ids"].append(s["id"])
        if s["submitter"] not in entry["submitters"]:
            entry["submitters"].append(s["submitter"])
        if s["note"]:
            entry["notes"].append((s["submitter"], s["note"]))
    return list(grouped.values())


def collect(cycle_id, settings=None):
    """Scores anything not yet scored, then ranks. Used for the real report."""
    settings = settings or db.get_settings()
    entries = _group(cycle_id)
    with ThreadPoolExecutor(max_workers=4) as pool:
        analyses = list(pool.map(lambda e: scorer.analyze(e["url"], settings, retry_failed=True), entries))
    items = [{**a, **e} for a, e in zip(analyses, entries)]
    return scorer.rank(items)


def preview(cycle_id):
    """Uses only already-finished scores, so the admin page loads instantly."""
    settings = db.get_settings()
    items = []
    for e in _group(cycle_id):
        cached = scorer.get_cached(e["url"], settings)
        items.append({**(cached or {"title": "", "overall": None, "eligible": False, "pending": True}), **e})
    return scorer.rank(items)


# ---------- Thursday report ----------
def build_report_file(cycle_id):
    settings = db.get_settings()
    items = collect(cycle_id, settings)
    os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
    path = os.path.join(Config.OUTPUT_DIR, f"Article-Submissions-{cycle_id}.docx")
    report.build_report(path, cycle_id, items, settings)
    return path, items


def send_report(cycle_id):
    settings = db.get_settings()
    recipients = db.parse_emails(settings["report_recipients"])
    path, items = build_report_file(cycle_id)
    top = sorted([i for i in items if i.get("rank")], key=lambda i: i["rank"])

    lines = [f"{i['rank']}. {i['title']} (sent by {', '.join(i['submitters'])})\n   {i['url']}" for i in top]
    text = (f"This week's article submissions are attached ({len(items)} links).\n\n"
            f"Suggested top {len(top)}:\n" + "\n".join(lines) +
            "\n\nThe full list, grouped by team member, is in the Word document.")
    rows = "".join(
        f"<li style='margin-bottom:8px'><a href='{html.escape(i['url'])}'><b>{html.escape(i['title'])}</b></a>"
        f"<br><span style='color:#5b6b6a'>Sent by {html.escape(', '.join(i['submitters']))}</span></li>"
        for i in top)
    body = (f"<p>This week's article submissions are attached ({len(items)} links).</p>"
            f"<p><b>Suggested top {len(top)}</b></p><ol>{rows}</ol>"
            "<p>The full list, grouped by team member, is in the Word document.</p>")

    with open(path, "rb") as fh:
        data = fh.read()
    return mailer.send_email(
        recipients, f"Article submissions for Friday: suggested top {len(top)} ({cyc.short_label(cycle_id)})",
        text, body, attachments=[(os.path.basename(path), data, mailer.DOCX_MIME)],
    )


# ---------- Monday reminder ----------
def send_reminder(cycle_id):
    settings = db.get_settings()
    team = db.parse_team(settings["team_members"])
    to = [p["email"] for p in team if p["email"]]
    cc = db.parse_emails(settings["reminder_cc"])
    link = Config.APP_URL + "/"
    deadline = cyc.label(cycle_id)
    text = (f"Hi all,\n\nPlease send your article picks for this Friday's client email by {deadline}.\n\n"
            f"Submit links here: {link}\n\nIt takes about 30 seconds. Paste one or more links, pick your "
            "name, and you're done.\n\nThanks!")
    body = (f"<p>Hi all,</p><p>Please send your article picks for this Friday's client email by "
            f"<b>{deadline}</b>.</p><p><a href='{link}' style='display:inline-block;padding:10px 18px;"
            f"background:#17282a;color:#ffffff;text-decoration:none;border-radius:4px'>Submit articles</a></p>"
            "<p>Paste one or more links, pick your name, and you're done.</p><p>Thanks!</p>")
    return mailer.send_email(to, "Reminder: article picks for Friday's client email", text, body, cc=cc)


# ---------- scheduler heartbeat (runs every 10 minutes; safe to run any number of times) ----------
def tick(now=None):
    now = now or cyc.now()
    settings = db.get_settings()
    done = []

    open_cycle = cyc.open_cycle(now)
    if settings["reminders_enabled"] == "1" and cyc.in_reminder_window(now):
        if db.claim_job("reminder", open_cycle):
            done.append(_run("reminder", open_cycle, send_reminder))

    closed_deadline = cyc.last_closed_deadline(now)
    closed_cycle = closed_deadline.date().isoformat()
    if settings["reports_enabled"] == "1" and now - closed_deadline < timedelta(days=2):
        if db.claim_job("report", closed_cycle):
            if not db.list_submissions(closed_cycle):
                db.record_job("report", closed_cycle, "skipped", "No submissions this week")
                done.append(("report", "skipped"))
            else:
                done.append(_run("report", closed_cycle, send_report))
    return done


def _run(job, cycle_id, fn):
    try:
        sent, message = fn(cycle_id)
        status = "sent" if sent else "saved"
    except Exception as exc:
        log.exception("%s job failed", job)
        status, message = "failed", str(exc)
    db.record_job(job, cycle_id, status, message)
    log.info("%s for %s: %s (%s)", job, cycle_id, status, message)
    return job, status
