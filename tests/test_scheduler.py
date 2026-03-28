# tests/test_scheduler.py
"""Tests for pipeline scheduler."""
from unittest.mock import patch, MagicMock
from scheduler import PipelineScheduler


def test_scheduler_init_default():
    sched = PipelineScheduler(run_pipeline_fn=lambda: None)
    assert sched.interval_hours == 4


def test_scheduler_update_interval():
    sched = PipelineScheduler(run_pipeline_fn=lambda: None)
    assert sched.update_interval(6) is True
    assert sched.interval_hours == 6


def test_scheduler_reject_below_min():
    sched = PipelineScheduler(run_pipeline_fn=lambda: None)
    assert sched.update_interval(0.5) is False


def test_scheduler_reject_above_max():
    sched = PipelineScheduler(run_pipeline_fn=lambda: None)
    assert sched.update_interval(200) is False


def test_scheduler_start_and_stop():
    called = []
    sched = PipelineScheduler(run_pipeline_fn=lambda: called.append(1))
    sched.start()
    assert sched.job is not None
    sched.stop()


def test_scheduler_update_interval_with_running_job():
    sched = PipelineScheduler(run_pipeline_fn=lambda: None)
    sched.start()
    assert sched.update_interval(8) is True
    assert sched.interval_hours == 8
    sched.stop()
