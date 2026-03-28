import json
import os
import tempfile
from state import PipelineState, load_state, save_state

def test_default_state():
    s = PipelineState()
    assert s.step == "init"
    assert s.raw_listing_count == 0
    assert s.approved_ids == []

def test_save_and_load(tmp_path):
    path = str(tmp_path / "state.json")
    s = PipelineState(step="analyzed", raw_listing_count=42)
    save_state(s, path)
    loaded = load_state(path)
    assert loaded.step == "analyzed"
    assert loaded.raw_listing_count == 42

def test_load_missing_file(tmp_path):
    path = str(tmp_path / "nonexistent.json")
    s = load_state(path)
    assert s.step == "init"

def test_state_is_fresh():
    from datetime import datetime, timezone
    s = PipelineState(last_scrape_at=datetime.now(timezone.utc).isoformat())
    assert s.is_data_fresh(max_hours=4) is True

def test_state_is_stale():
    s = PipelineState(last_scrape_at="2020-01-01T00:00:00+00:00")
    assert s.is_data_fresh(max_hours=4) is False

def test_state_no_scrape_is_stale():
    s = PipelineState()
    assert s.is_data_fresh(max_hours=4) is False


def test_state_is_data_fresh_malformed_timestamp():
    """Malformed ISO timestamp → False (not crash)."""
    s = PipelineState(last_scrape_at="not-a-date")
    assert s.is_data_fresh(max_hours=4) is False


def test_load_corrupted_json_file(tmp_path):
    """Corrupted JSON file → default state."""
    path = str(tmp_path / "bad.json")
    with open(path, "w") as f:
        f.write("{this is not valid json!!!")
    s = load_state(path)
    assert s.step == "init"


def test_state_is_data_fresh_naive_timestamp():
    """Timezone-naive timestamp → TypeError caught → False."""
    s = PipelineState(last_scrape_at="2026-03-28T12:00:00")
    assert s.is_data_fresh(max_hours=999) is False


def test_load_valid_json_invalid_schema(tmp_path):
    """Valid JSON but wrong schema → Pydantic ValidationError → default state."""
    path = str(tmp_path / "bad_schema.json")
    with open(path, "w") as f:
        f.write('{"step": 12345, "unknown_field": true}')
    s = load_state(path)
    assert s.step == "init"
