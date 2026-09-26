"""Web app: a one-page submission form for the team, plus an admin page for Adam and Megan."""
import hmac
import logging
import os
import re
from functools import wraps

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request, send_file,
                   session, url_for)

import cycle as cyc
import db
import jobs
from config import Config
from fetcher import is_valid_url, normalize_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
MAX_LINKS_PER_SUBMIT = 15


def create_app(start_scheduler=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    db.init_db()

    @app.context_processor
    def inject_globals():
        return {"firm_name": Config.FIRM_NAME, "is_admin": session.get("admin", False)}

    def admin_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not session.get("admin"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapper

    # ---------------- team submission page ----------------
    def render_form(status=200, **form):
        settings = db.get_settings()
        cycle_id = cyc.open_cycle()
        subs = db.list_submissions(cycle_id)
        name = form.get("submitter") or request.cookies.get("submitter", "")
        mine = [s for s in subs if s["submitter"] == name] if name else []
        return render_template(
            "submit.html", team=db.parse_team(settings["team_members"]), deadline=cyc.label(cycle_id),
            total=len(subs), mine=mine, selected=name, links=form.get("links", ""),
            note=form.get("note", ""), need_code=bool(Config.TEAM_ACCESS_CODE),
        ), status

    @app.get("/")
    def submit_form():
        return render_form()

    @app.post("/")
    def submit():
        team_names = [p["name"] for p in db.parse_team(db.get_settings()["team_members"])]
        name = request.form.get("submitter", "").strip()
        raw = request.form.get("links", "")
        note = request.form.get("note", "").strip()[:500]
        keep = {"submitter": name, "links": raw, "note": note}

        if Config.TEAM_ACCESS_CODE and not hmac.compare_digest(
                request.form.get("code", "").strip(), Config.TEAM_ACCESS_CODE):
            flash("That team code isn't right. Ask Megan for the current code.", "error")
            return render_form(400, **keep)
        if name not in team_names:
            flash("Choose your name from the list.", "error")
            return render_form(400, **keep)

        urls, bad = [], []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            candidates = [t for t in re.split(r"[\s,]+", line) if "." in t or "://" in t]
            found = [normalize_url(t) for t in candidates if is_valid_url(normalize_url(t))]
            if found:
                urls.extend(found)
            else:
                bad.append(line[:60])
        urls = list(dict.fromkeys(urls))
        if not urls:
            flash("Paste at least one link, starting with https://", "error")
            return render_form(400, **keep)
        if len(urls) > MAX_LINKS_PER_SUBMIT:
            flash(f"Please send {MAX_LINKS_PER_SUBMIT} links or fewer at a time.", "error")
            return render_form(400, **keep)

        cycle_id = cyc.open_cycle()
        added = [u for u in urls if db.add_submission(cycle_id, name, u, note)]
        jobs.queue_analysis(added)

        if added:
            flash(f"Thanks, {name.split()[0]}. {len(added)} link{'s' if len(added) != 1 else ''} added "
                  f"for this week.", "success")
        if len(added) < len(urls):
            flash(f"{len(urls) - len(added)} link{'s were' if len(urls) - len(added) != 1 else ' was'} "
                  "already on your list this week, so we skipped the duplicate.", "info")
        if bad:
            flash(f"Skipped {len(bad)} line{'s' if len(bad) != 1 else ''} that didn't look like a link: "
                  + "; ".join(f'"{b}"' for b in bad[:3]), "error")

        resp = redirect(url_for("submit_form"))
        resp.set_cookie("submitter", name, max_age=365 * 24 * 3600, samesite="Lax")
        return resp

    # ---------------- admin ----------------
    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if hmac.compare_digest(request.form.get("password", ""), Config.ADMIN_PASSWORD):
                session["admin"] = True
                session.permanent = True
                target = request.args.get("next", "")
                return redirect(target if target.startswith("/admin") else url_for("admin"))
            flash("Wrong password.", "error")
        return render_template("login.html")

    @app.post("/admin/logout")
    def logout():
        session.clear()
        return redirect(url_for("submit_form"))

    @app.get("/admin")
    @admin_required
    def admin():
        open_cycle = cyc.open_cycle()
        cycles = sorted(set(db.list_cycles()) | {open_cycle}, reverse=True)
        cycle_id = request.args.get("week", open_cycle)
        if cycle_id not in cycles:
            cycle_id = open_cycle
        items = jobs.preview(cycle_id)
        items.sort(key=lambda i: (i.get("rank") or 99, -(i.get("overall") or -1)))
        settings = db.get_settings()
        return render_template(
            "admin.html", items=items, cycle_id=cycle_id, cycles=cycles, open_cycle=open_cycle,
            label=cyc.label, short_label=cyc.short_label, runs=db.recent_runs(),
            pending=sum(1 for i in items if i.get("pending")),
            recipients=db.parse_emails(settings["report_recipients"]),
            ai_on=bool(Config.ANTHROPIC_API_KEY), email_on=bool(Config.SMTP_HOST),
            team_count=len(db.parse_team(settings["team_members"])),
        )

    @app.post("/admin/submissions/delete")
    @admin_required
    def delete_submission():
        ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
        for sub_id in ids:
            db.delete_submission(sub_id)
        flash("Link removed from this week.", "success")
        return redirect(request.referrer or url_for("admin"))

    @app.get("/admin/report/<cycle_id>")
    @admin_required
    def download_report(cycle_id):
        _check_cycle(cycle_id)
        path, _ = jobs.build_report_file(cycle_id)
        return send_file(os.path.abspath(path), as_attachment=True, download_name=os.path.basename(path))

    @app.post("/admin/report/<cycle_id>/email")
    @admin_required
    def email_report(cycle_id):
        _check_cycle(cycle_id)
        sent, message = jobs.send_report(cycle_id)
        db.record_job("report", cycle_id, "sent" if sent else "saved", message)
        flash(("Report emailed. " if sent else "") + message, "success" if sent else "info")
        return redirect(url_for("admin", week=cycle_id))

    @app.post("/admin/reminder")
    @admin_required
    def email_reminder():
        cycle_id = cyc.open_cycle()
        sent, message = jobs.send_reminder(cycle_id)
        db.record_job("reminder", cycle_id, "sent" if sent else "saved", message)
        flash(("Reminder sent. " if sent else "") + message, "success" if sent else "info")
        return redirect(url_for("admin"))

    @app.post("/admin/rescore/<cycle_id>")
    @admin_required
    def rescore(cycle_id):
        _check_cycle(cycle_id)
        urls = list({s["url"] for s in db.list_submissions(cycle_id)})
        jobs.queue_analysis(urls, refresh=True)
        flash(f"Re-scoring {len(urls)} links in the background. Refresh in a minute.", "info")
        return redirect(url_for("admin", week=cycle_id))

    @app.route("/admin/settings", methods=["GET", "POST"])
    @admin_required
    def settings_page():
        if request.method == "POST":
            form = request.form
            db.save_settings({
                "team_members": form.get("team_members", "").strip(),
                "report_recipients": form.get("report_recipients", "").strip(),
                "reminder_cc": form.get("reminder_cc", "").strip(),
                "worldview": form.get("worldview", "").strip(),
                "past_examples": form.get("past_examples", "").strip(),
                "extra_paywall_domains": form.get("extra_paywall_domains", "").strip(),
                "reminders_enabled": "1" if form.get("reminders_enabled") else "0",
                "reports_enabled": "1" if form.get("reports_enabled") else "0",
            })
            flash("Settings saved.", "success")
            return redirect(url_for("settings_page"))
        return render_template("settings.html", s=db.get_settings(),
                               team=db.parse_team(db.get_settings()["team_members"]))

    # ---------------- ops ----------------
    @app.get("/tasks/tick")
    def external_tick():
        """Optional: lets a free outside cron service wake the app so jobs never get missed."""
        if not Config.CRON_KEY or not hmac.compare_digest(request.args.get("key", ""), Config.CRON_KEY):
            abort(403)
        return jsonify(done=jobs.tick())

    @app.get("/healthz")
    def health():
        return jsonify(ok=True)

    def _check_cycle(cycle_id):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cycle_id):
            abort(404)

    if start_scheduler is None:
        start_scheduler = Config.ENABLE_SCHEDULER
    if start_scheduler and (not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        import scheduler
        scheduler.start()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
