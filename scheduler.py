"""Runs jobs.tick() every 10 minutes inside the web app.

tick() decides whether the Monday reminder or Thursday report is due and records each send,
so a restart, a sleeping server, or two copies of the app never cause a double send."""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import cycle as cyc
import jobs
from config import Config

log = logging.getLogger("digest.scheduler")
_scheduler = None


def start():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone=Config.TIMEZONE)
    _scheduler.add_job(jobs.tick, "interval", minutes=10, id="tick", coalesce=True, max_instances=1,
                       next_run_time=datetime.now(cyc.tz()) + timedelta(seconds=30))
    _scheduler.start()
    log.info("Scheduler started (checks every 10 minutes, timezone %s)", Config.TIMEZONE)
    return _scheduler
