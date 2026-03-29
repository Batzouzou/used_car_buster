# tests/test_monitor.py
"""Tests for the Flask monitor dashboard."""
import json
import pytest
from unittest.mock import patch
from pathlib import Path

from monitor import create_monitor_app, _load_state_dict, _load_latest_json


@pytest.fixture
def client(tmp_path):
    """Flask test client with OUTPUT_DIR pointed at empty tmp_path."""
    with patch("monitor.OUTPUT_DIR", str(tmp_path)):
        app = create_monitor_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


@pytest.fixture
def populated_dir(tmp_path):
    """Tmp dir populated with sample state, raw, approved, and priced JSON."""
    state = {
        "step": "priced",
        "last_scrape_at": "2026-03-28T12:00:00Z",
        "raw_listing_count": 5,
    }
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")

    raw = [
        {"id": "lbc_1", "platform": "leboncoin", "title": "Toyota iQ CVT",
         "price": 3200, "year": 2011, "mileage_km": 78000, "city": "Paris",
         "seller_type": "pro"},
        {"id": "lc_2", "platform": "lacentrale", "title": "Toyota iQ Auto",
         "price": 4100, "year": 2012, "mileage_km": 65000, "city": "Lyon",
         "seller_type": "private"},
    ]
    (tmp_path / "raw_listings_20260328.json").write_text(
        json.dumps(raw), encoding="utf-8"
    )

    approved = [
        {"id": "lbc_1", "title": "Toyota iQ CVT", "price": 3200, "year": 2011,
         "mileage_km": 78000, "score": 82, "city": "Paris", "seller_type": "pro"},
    ]
    (tmp_path / "approved_20260328.json").write_text(
        json.dumps(approved), encoding="utf-8"
    )

    priced = [
        {"id": "lbc_1", "title": "Toyota iQ CVT", "price": 3200,
         "market_estimate_low": 2800, "market_estimate_high": 3500,
         "opening_offer": 2600, "max_acceptable": 3100},
    ]
    (tmp_path / "priced_20260328.json").write_text(
        json.dumps(priced), encoding="utf-8"
    )

    return tmp_path


@pytest.fixture
def pop_client(populated_dir):
    """Flask test client with OUTPUT_DIR pointed at populated tmp dir."""
    with patch("monitor.OUTPUT_DIR", str(populated_dir)):
        app = create_monitor_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# --- Dashboard route ---

def test_dashboard_no_data(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"No pipeline state" in resp.data


def test_dashboard_with_data(pop_client):
    resp = pop_client.get("/")
    assert resp.status_code == 200
    assert b"priced" in resp.data
    assert b"raw_listing_count" in resp.data


# --- Shortlist route ---

def test_shortlist_no_data(client):
    resp = client.get("/shortlist")
    assert resp.status_code == 200
    assert b"No data available" in resp.data


def test_shortlist_with_data(pop_client):
    resp = pop_client.get("/shortlist")
    assert resp.status_code == 200
    assert b"lbc_1" in resp.data
    assert b"82" in resp.data


# --- Raw route ---

def test_raw_no_data(client):
    resp = client.get("/raw")
    assert resp.status_code == 200
    assert b"No data available" in resp.data


def test_raw_with_data(pop_client):
    resp = pop_client.get("/raw")
    assert resp.status_code == 200
    assert b"lbc_1" in resp.data
    assert b"leboncoin" in resp.data


# --- Priced route ---

def test_priced_no_data(client):
    resp = client.get("/priced")
    assert resp.status_code == 200
    assert b"No data available" in resp.data


def test_priced_with_data(pop_client):
    resp = pop_client.get("/priced")
    assert resp.status_code == 200
    assert b"2800" in resp.data
    assert b"3100" in resp.data


# --- API state ---

def test_api_state_no_data(client):
    resp = client.get("/api/state")
    assert resp.status_code == 200
    assert resp.get_json() == {}


def test_api_state_with_data(pop_client):
    resp = pop_client.get("/api/state")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["step"] == "priced"
    assert data["raw_listing_count"] == 5


# --- API listings ---

def test_api_listings_no_data(client):
    resp = client.get("/api/listings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"raw": [], "approved": [], "priced": []}


def test_api_listings_with_data(pop_client):
    resp = pop_client.get("/api/listings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["raw"]) == 2
    assert len(data["approved"]) == 1
    assert len(data["priced"]) == 1


# --- Helper function tests ---

def test_load_state_dict_missing_file(tmp_path):
    with patch("monitor.OUTPUT_DIR", str(tmp_path)):
        assert _load_state_dict() == {}


def test_load_state_dict_corrupt_file(tmp_path):
    (tmp_path / "state.json").write_text("not json", encoding="utf-8")
    with patch("monitor.OUTPUT_DIR", str(tmp_path)):
        assert _load_state_dict() == {}


def test_load_latest_json_no_files(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    with patch("monitor.OUTPUT_DIR", str(tmp_path)):
        assert _load_latest_json("raw_listings") == []


def test_load_latest_json_picks_most_recent(tmp_path):
    (tmp_path / "raw_listings_20260327.json").write_text('[{"old": true}]', encoding="utf-8")
    (tmp_path / "raw_listings_20260328.json").write_text('[{"new": true}]', encoding="utf-8")
    with patch("monitor.OUTPUT_DIR", str(tmp_path)):
        result = _load_latest_json("raw_listings")
        assert result == [{"new": True}]


def test_load_latest_json_corrupt_file(tmp_path):
    (tmp_path / "raw_listings_20260328.json").write_text("bad", encoding="utf-8")
    with patch("monitor.OUTPUT_DIR", str(tmp_path)):
        assert _load_latest_json("raw_listings") == []


def test_load_latest_json_non_list(tmp_path):
    """JSON file contains object instead of array → returns empty list."""
    (tmp_path / "raw_listings_20260328.json").write_text('{"key": "val"}', encoding="utf-8")
    with patch("monitor.OUTPUT_DIR", str(tmp_path)):
        assert _load_latest_json("raw_listings") == []
