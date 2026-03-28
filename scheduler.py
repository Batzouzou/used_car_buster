# scheduler.py
"""Configurable pipeline scheduler using APScheduler."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import DEFAULT_INTERVAL_HOURS, MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS

logger = logging.getLogger(__name__)


class PipelineScheduler:
    """Schedule pipeline runs at configurable intervals."""

    def __init__(self, run_pipeline_fn, interval_hours=DEFAULT_INTERVAL_HOURS):
        self.scheduler = BackgroundScheduler()
        self.run_pipeline_fn = run_pipeline_fn
        self.interval_hours = interval_hours
        self.job = None

    def start(self):
        """Start the scheduler."""
        self.job = self.scheduler.add_job(
            self.run_pipeline_fn,
            trigger=IntervalTrigger(hours=self.interval_hours),
            id="pipeline_run",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(f"Scheduler started: pipeline every {self.interval_hours}h")

    def update_interval(self, hours: float) -> bool:
        """Update the schedule interval. Returns False if out of range."""
        if hours < MIN_INTERVAL_HOURS or hours > MAX_INTERVAL_HOURS:
            return False
        self.interval_hours = hours
        if self.job:
            self.job.reschedule(trigger=IntervalTrigger(hours=hours))
            logger.info(f"Scheduler interval updated to {hours}h")
        return True

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
