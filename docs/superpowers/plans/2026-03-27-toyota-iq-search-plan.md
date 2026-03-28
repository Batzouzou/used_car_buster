# Toyota iQ Agentic Car Search — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an agentic tool that scrapes 4 French used car platforms for Toyota iQ automatics, scores them, presents shortlists via Telegram + terminal, generates negotiation messages, and runs on a configurable schedule.

**Architecture:** Single long-running process. Telegram bot (polling) + APScheduler + agentic pipeline. Supervisor Agent (Claude Sonnet tool_use loop) orchestrates 4 Scrapers, Analyst (Ollama/Haiku), and Pricer (Sonnet). HITL via Telegram (friend primary, Jerome mirror) + terminal (dev). Pydantic v2 typed data flow.

**UI Language:** All Telegram-facing text MUST be in French — command names (`/chercher`, `/liste`, `/approuver`, `/rejeter`, `/details`, `/intervalle`, `/statut`), bot responses, menus, alerts, and negotiation messages. No English in user-facing output.

**Tech Stack:** Python 3.x, requests, beautifulsoup4, anthropic, pydantic v2, python-dotenv, python-telegram-bot, apscheduler, Ollama (local LLM)

**Spec:** `docs/superpowers/specs/2026-03-27-toyota-iq-search-design.md`

---

## Chunk 1: Foundation (Tasks 1-4)

### Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Create requirements.txt**

```
requests
beautifulsoup4
anthropic
pydantic>=2.0
python-dotenv
python-telegram-bot>=20.0
apscheduler>=3.10
pytest
```

- [ ] **Step 2: Create .env.example**

```
ANTHROPIC_API_KEY=sk-ant-xxx
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
TELEGRAM_FRIEND_CHAT_ID=123456789
TELEGRAM_JEROME_CHAT_ID=987654321
```

- [ ] **Step 3: Create .gitignore**

```
.env
_IQ/*.json
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Write failing test for config**

```python
# tests/test_config.py
from config import (
    SEARCH_CRITERIA, DISTANCE_ZONES, ORLY_LAT, ORLY_LON,
    PLATFORMS, CACHE_FRESHNESS_HOURS, SCORING_WEIGHTS,
    LLM_MAX_RETRIES, OLLAMA_MODEL
)

def test_search_criteria_locked():
    assert SEARCH_CRITERIA["make"] == "Toyota"
    assert SEARCH_CRITERIA["model"] == "iQ"
    assert SEARCH_CRITERIA["transmission"] == "automatic"
    assert SEARCH_CRITERIA["max_price"] == 5000
    assert SEARCH_CRITERIA["max_mileage_km"] == 150000
    assert SEARCH_CRITERIA["min_year"] == 2009

def test_orly_coordinates():
    assert abs(ORLY_LAT - 48.7262) < 0.001
    assert abs(ORLY_LON - 2.3652) < 0.001

def test_distance_zones():
    assert DISTANCE_ZONES["PRIME"]["max_km"] == 20
    assert DISTANCE_ZONES["PRIME"]["bonus"] == 15
    assert DISTANCE_ZONES["NEAR"]["max_km"] == 30
    assert DISTANCE_ZONES["NEAR"]["bonus"] == 8
    assert DISTANCE_ZONES["FAR"]["max_km"] == 40
    assert DISTANCE_ZONES["FAR"]["bonus"] == 3
    assert DISTANCE_ZONES["REMOTE"]["bonus"] == 0

def test_scoring_weights_sum_to_100():
    total = sum(SCORING_WEIGHTS.values())
    assert total == 100

def test_cache_freshness():
    assert CACHE_FRESHNESS_HOURS == 4

def test_ollama_model_configurable():
    assert isinstance(OLLAMA_MODEL, str)
    assert len(OLLAMA_MODEL) > 0
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_config.py -v`
Expected: FAIL — cannot import config

- [ ] **Step 6: Implement config.py**

```python
# config.py
"""Search criteria, constants, and configuration."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Search Criteria (locked) ---
SEARCH_CRITERIA = {
    "make": "Toyota",
    "model": "iQ",
    "transmission": "automatic",
    "max_price": 5000,
    "max_mileage_km": 150000,
    "min_year": 2009,
}

# --- Reference point: Orly airport ---
ORLY_LAT = 48.7262
ORLY_LON = 2.3652

# --- Distance zones ---
DISTANCE_ZONES = {
    "PRIME":  {"max_km": 20,  "bonus": 15},
    "NEAR":   {"max_km": 30,  "bonus": 8},
    "FAR":    {"max_km": 40,  "bonus": 3},
    "REMOTE": {"max_km": 9999, "bonus": 0},
}

# --- Scoring weights (must sum to 100) ---
SCORING_WEIGHTS = {
    "price": 30,
    "mileage": 20,
    "year": 15,
    "proximity": 15,
    "condition": 10,
    "transmission": 10,
}

# --- Platforms ---
PLATFORMS = ["leboncoin", "lacentrale", "leparking", "autoscout24"]

# --- Cache ---
CACHE_FRESHNESS_HOURS = 4

# --- LLM ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
LLM_MAX_RETRIES = 2

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_FRIEND_CHAT_ID = os.getenv("TELEGRAM_FRIEND_CHAT_ID", "")
TELEGRAM_JEROME_CHAT_ID = os.getenv("TELEGRAM_JEROME_CHAT_ID", "")

# --- Scheduler ---
DEFAULT_INTERVAL_HOURS = 4
MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 168  # 1 week

# --- Output directory ---
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "_IQ")
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .env.example .gitignore config.py tests/test_config.py
git commit -m "feat: project setup and config module"
```

---

### Task 2: Data Models

**Files:**
- Create: `models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for models**

```python
# tests/test_models.py
import pytest
from datetime import datetime, timezone
from models import RawListing, ScoredListing, PricedListing, ScoreBreakdown

# --- RawListing ---

def test_raw_listing_valid():
    listing = RawListing(
        id="lbc_123",
        platform="leboncoin",
        title="Toyota iQ 1.33 CVT",
        price=3200,
        year=2011,
        mileage_km=78000,
        transmission="auto",
        fuel="essence",
        city="Paris",
        department="75",
        lat=48.85,
        lon=2.35,
        seller_type="pro",
        url="https://www.leboncoin.fr/voitures/123",
        description="Bon etat",
        images=["img1.jpg"],
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
    assert listing.id == "lbc_123"
    assert listing.platform == "leboncoin"

def test_raw_listing_optional_fields():
    listing = RawListing(
        id="lc_456",
        platform="lacentrale",
        title="iQ auto",
        price=2800,
        year=2010,
        seller_type="private",
        url="https://www.lacentrale.fr/auto/456",
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
    assert listing.mileage_km is None
    assert listing.lat is None
    assert listing.images == []

def test_raw_listing_rejects_negative_price():
    with pytest.raises(Exception):
        RawListing(
            id="x", platform="leboncoin", title="x", price=-100,
            year=2010, seller_type="pro", url="http://x",
            scraped_at=datetime.now(timezone.utc).isoformat(),
        )

# --- ScoreBreakdown ---

def test_score_breakdown_valid():
    bd = ScoreBreakdown(price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10)
    assert bd.price == 25

def test_score_breakdown_condition_capped_at_10():
    bd = ScoreBreakdown(price=0, mileage=0, year=0, proximity=0, condition=15, transmission=0)
    assert bd.condition == 10  # capped

# --- ScoredListing ---

def test_scored_listing_valid():
    raw = RawListing(
        id="lbc_1", platform="leboncoin", title="iQ", price=3000,
        year=2012, seller_type="pro", url="http://x",
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
    scored = ScoredListing(
        **raw.model_dump(),
        score=78,
        score_breakdown=ScoreBreakdown(
            price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10
        ),
        excluded=False,
        red_flags=[],
        highlights=["CT OK"],
        concerns=[],
        summary_fr="Bonne affaire",
    )
    assert scored.score == 78
    assert scored.excluded is False

def test_scored_listing_excluded():
    raw = RawListing(
        id="lbc_2", platform="leboncoin", title="iQ manuelle", price=3000,
        year=2012, seller_type="private", url="http://x",
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
    scored = ScoredListing(
        **raw.model_dump(),
        score=-1,
        score_breakdown=ScoreBreakdown(
            price=0, mileage=0, year=0, proximity=0, condition=0, transmission=0
        ),
        excluded=True,
        exclusion_reason="Manual transmission",
        red_flags=["manual"],
        highlights=[],
        concerns=[],
        summary_fr="Exclue: manuelle",
    )
    assert scored.excluded is True
    assert scored.exclusion_reason == "Manual transmission"

# --- PricedListing ---

def test_priced_listing_valid():
    raw = RawListing(
        id="lbc_1", platform="leboncoin", title="iQ", price=3000,
        year=2012, seller_type="pro", url="http://x",
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
    scored = ScoredListing(
        **raw.model_dump(),
        score=78,
        score_breakdown=ScoreBreakdown(
            price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10
        ),
        excluded=False, red_flags=[], highlights=[], concerns=[],
        summary_fr="OK",
    )
    priced = PricedListing(
        **scored.model_dump(),
        market_estimate_low=2500,
        market_estimate_high=3200,
        opening_offer=2400,
        max_acceptable=3000,
        anchors=["km eleve"],
        message_digital="Bonjour...",
        message_oral_points=["Mentionner km"],
    )
    assert priced.opening_offer == 2400
    assert priced.market_estimate_low < priced.market_estimate_high
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_models.py -v`
Expected: FAIL — cannot import models

- [ ] **Step 3: Implement models.py**

```python
# models.py
"""Pydantic v2 data models for the pipeline."""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class RawListing(BaseModel):
    """Raw listing scraped from a platform."""
    id: str
    platform: str
    title: str
    price: int = Field(ge=0)
    year: int = Field(ge=2000, le=2030)
    mileage_km: Optional[int] = Field(default=None, ge=0)
    transmission: Optional[str] = None
    fuel: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    seller_type: str = "unknown"
    url: str
    description: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    scraped_at: str


class ScoreBreakdown(BaseModel):
    """Breakdown of the 100-point scoring rubric."""
    price: int = Field(ge=0, le=30)
    mileage: int = Field(ge=0, le=20)
    year: int = Field(ge=0, le=15)
    proximity: int = Field(ge=0, le=15)
    condition: int = Field(ge=-10, le=10)
    transmission: int = Field(ge=-100, le=10)

    @field_validator("condition", mode="before")
    @classmethod
    def cap_condition(cls, v: int) -> int:
        return min(v, 10)


class ScoredListing(RawListing):
    """Listing with analyst score."""
    score: int = Field(ge=-1, le=100)
    score_breakdown: ScoreBreakdown
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    red_flags: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    summary_fr: str = ""


class PricedListing(ScoredListing):
    """Listing with pricing and negotiation data."""
    market_estimate_low: int = Field(ge=0)
    market_estimate_high: int = Field(ge=0)
    opening_offer: int = Field(ge=0)
    max_acceptable: int = Field(ge=0)
    anchors: list[str] = Field(default_factory=list)
    message_digital: str = ""
    message_oral_points: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_models.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: pydantic v2 data models"
```

---

### Task 3: Utilities

**Files:**
- Create: `utils.py`
- Test: `tests/test_utils.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_utils.py
from utils import haversine_km, get_distance_zone, clean_text, extract_json_from_text

def test_haversine_paris_orly():
    # Paris center to Orly ~ 14 km
    dist = haversine_km(48.8566, 2.3522, 48.7262, 2.3652)
    assert 13 < dist < 16

def test_haversine_same_point():
    assert haversine_km(48.0, 2.0, 48.0, 2.0) == 0.0

def test_distance_zone_prime():
    assert get_distance_zone(10) == "PRIME"

def test_distance_zone_near():
    assert get_distance_zone(25) == "NEAR"

def test_distance_zone_far():
    assert get_distance_zone(35) == "FAR"

def test_distance_zone_remote():
    assert get_distance_zone(100) == "REMOTE"

def test_clean_text():
    assert clean_text("  Hello   World  ") == "Hello World"
    assert clean_text(None) == ""
    assert clean_text("") == ""

def test_extract_json_simple():
    text = 'Some preamble {"key": "value"} trailing'
    result = extract_json_from_text(text)
    assert result == {"key": "value"}

def test_extract_json_array():
    text = 'blah [{"a": 1}] blah'
    result = extract_json_from_text(text)
    assert result == [{"a": 1}]

def test_extract_json_none_on_failure():
    result = extract_json_from_text("no json here")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_utils.py -v`
Expected: FAIL

- [ ] **Step 3: Implement utils.py**

```python
# utils.py
"""Utility functions: distance, geocoding, text cleanup, JSON extraction."""
import json
import math
import re
from config import DISTANCE_ZONES


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two GPS points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_distance_zone(distance_km: float) -> str:
    """Return zone name based on distance from Orly."""
    for zone_name in ["PRIME", "NEAR", "FAR"]:
        if distance_km <= DISTANCE_ZONES[zone_name]["max_km"]:
            return zone_name
    return "REMOTE"


def get_proximity_bonus(distance_km: float) -> int:
    """Return scoring bonus for distance zone."""
    zone = get_distance_zone(distance_km)
    return DISTANCE_ZONES[zone]["bonus"]


def clean_text(text: str | None) -> str:
    """Normalize whitespace, strip."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def extract_json_from_text(text: str):
    """Extract first JSON object or array from LLM text output."""
    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Find first { or [
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    break
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_utils.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_utils.py
git commit -m "feat: utility functions (haversine, geocoding, text, json)"
```

---

### Task 4: State Persistence

**Files:**
- Create: `state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_state.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_state.py -v`
Expected: FAIL

- [ ] **Step 3: Implement state.py**

```python
# state.py
"""Pipeline state persistence."""
import json
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional


class PipelineState(BaseModel):
    """Tracks pipeline progress. Saved to JSON after every supervisor action."""
    step: str = "init"
    last_scrape_at: Optional[str] = None
    last_scrape_platforms: list[str] = Field(default_factory=list)
    raw_listing_count: int = 0
    analysis_status: str = "pending"  # pending | done | failed
    shortlist_pro_count: int = 0
    shortlist_part_count: int = 0
    approved_ids: list[str] = Field(default_factory=list)
    pricing_status: str = "pending"  # pending | done | failed

    def is_data_fresh(self, max_hours: int = 4) -> bool:
        if not self.last_scrape_at:
            return False
        try:
            scrape_time = datetime.fromisoformat(self.last_scrape_at)
            now = datetime.now(timezone.utc)
            return (now - scrape_time).total_seconds() < max_hours * 3600
        except (ValueError, TypeError):
            return False


def load_state(path: str) -> PipelineState:
    """Load state from JSON file, or return default if missing."""
    p = Path(path)
    if not p.exists():
        return PipelineState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return PipelineState.model_validate(data)
    except (json.JSONDecodeError, Exception):
        return PipelineState()


def save_state(state: PipelineState, path: str) -> None:
    """Save state to JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(state.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_state.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add state.py tests/test_state.py
git commit -m "feat: pipeline state persistence"
```

---

## Chunk 2: LLM Client & Scrapers (Tasks 5-7)

### Task 5: LLM Client

**Files:**
- Create: `llm_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_llm_client.py
import pytest
from unittest.mock import patch, MagicMock
from llm_client import LLMClient, LLMResponse

def test_llm_response_model():
    r = LLMResponse(text="hello", model_used="ollama", raw=None)
    assert r.text == "hello"
    assert r.model_used == "ollama"

def test_client_init():
    client = LLMClient()
    assert client is not None

@patch("llm_client.requests.post")
def test_query_ollama_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": '{"score": 75}'}
    }
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    client = LLMClient()
    result = client.query(
        messages=[{"role": "user", "content": "Score this"}],
        model_preference="local",
    )
    assert result.text == '{"score": 75}'
    assert result.model_used == "ollama"

@patch("llm_client.requests.post")
def test_query_ollama_fallback_to_haiku(mock_post):
    # Ollama fails
    mock_post.side_effect = Exception("Ollama down")

    client = LLMClient()
    with patch.object(client, "_query_anthropic") as mock_anthropic:
        mock_anthropic.return_value = LLMResponse(
            text="fallback response", model_used="claude-haiku-4-5-20251001", raw=None
        )
        result = client.query(
            messages=[{"role": "user", "content": "test"}],
            model_preference="local",
        )
        assert result.model_used == "claude-haiku-4-5-20251001"

@patch("llm_client.anthropic")
def test_query_sonnet_direct(mock_anthropic_mod):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="sonnet response")]
    mock_msg.model = "claude-sonnet-4-20250514"
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic_mod.Anthropic.return_value = mock_client

    client = LLMClient()
    client._anthropic_client = mock_client
    result = client.query(
        messages=[{"role": "user", "content": "test"}],
        model_preference="sonnet",
    )
    assert "sonnet" in result.model_used

def test_query_with_tools_sonnet():
    """Supervisor needs tool_use mode. Verify the client accepts tools param."""
    client = LLMClient()
    # Just verify the method signature accepts tools — actual API call is mocked in integration
    assert callable(client.query_with_tools)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_llm_client.py -v`
Expected: FAIL

- [ ] **Step 3: Implement llm_client.py**

```python
# llm_client.py
"""Unified LLM client: Ollama (local) + Anthropic (cloud) with auto-fallback."""
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import anthropic
import requests

from config import (
    ANTHROPIC_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL, LLM_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

FALLBACK_CHAINS = {
    "local": ["ollama", "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
    "haiku": ["claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
    "sonnet": ["claude-sonnet-4-20250514"],
}

@dataclass
class LLMResponse:
    text: str
    model_used: str
    raw: Any


class LLMClient:
    """Unified interface for Ollama and Anthropic models."""

    def __init__(self):
        self._anthropic_client = None
        if ANTHROPIC_API_KEY:
            self._anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def query(
        self,
        messages: list[dict],
        model_preference: str = "local",
        system: str | None = None,
    ) -> LLMResponse:
        """Send messages to LLM with automatic fallback chain."""
        chain = FALLBACK_CHAINS.get(model_preference, FALLBACK_CHAINS["local"])
        last_error = None

        for model in chain:
            for attempt in range(LLM_MAX_RETRIES + 1):
                try:
                    if model == "ollama":
                        return self._query_ollama(messages, system)
                    else:
                        return self._query_anthropic(messages, model, system)
                except Exception as e:
                    last_error = e
                    logger.warning(f"{model} attempt {attempt+1} failed: {e}")
                    if attempt < LLM_MAX_RETRIES:
                        time.sleep(2 ** attempt)

        raise RuntimeError(f"All LLM models failed. Last error: {last_error}")

    def query_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> dict:
        """Send messages with tool definitions (Anthropic tool_use API only)."""
        if not self._anthropic_client:
            raise RuntimeError("Anthropic API key required for tool_use")

        kwargs = {
            "model": model,
            "max_tokens": 4096,
            "messages": messages,
            "tools": tools,
        }
        if system:
            kwargs["system"] = system

        response = self._anthropic_client.messages.create(**kwargs)
        return {
            "content": response.content,
            "stop_reason": response.stop_reason,
            "model": response.model,
            "raw": response,
        }

    def _query_ollama(
        self, messages: list[dict], system: str | None = None
    ) -> LLMResponse:
        """Query Ollama local LLM via /api/chat endpoint."""
        ollama_messages = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        ollama_messages.extend(messages)

        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": ollama_messages, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(
            text=data["message"]["content"],
            model_used="ollama",
            raw=data,
        )

    def _query_anthropic(
        self, messages: list[dict], model: str, system: str | None = None
    ) -> LLMResponse:
        """Query Anthropic API."""
        if not self._anthropic_client:
            raise RuntimeError("No Anthropic API key configured")

        kwargs = {"model": model, "max_tokens": 4096, "messages": messages}
        if system:
            kwargs["system"] = system

        response = self._anthropic_client.messages.create(**kwargs)
        text = response.content[0].text if response.content else ""
        return LLMResponse(text=text, model_used=model, raw=response)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_llm_client.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add llm_client.py tests/test_llm_client.py
git commit -m "feat: unified LLM client with Ollama + Anthropic fallback"
```

---

### Task 6: LeBonCoin Scraper

**Files:**
- Create: `scraper_lbc.py`
- Create: `tests/fixtures/` (directory)
- Create: `tests/fixtures/lbc_sample.json`
- Test: `tests/test_scraper_lbc.py`

- [ ] **Step 1: Create test fixture**

```json
// tests/fixtures/lbc_sample.json
{
  "ads": [
    {
      "list_id": 12345,
      "subject": "Toyota iQ 1.33 CVT Automatique",
      "price": [3200],
      "attributes": [
        {"key": "mileage", "value": "78000"},
        {"key": "regdate", "value": "2011"},
        {"key": "fuel", "value": "1"},
        {"key": "gearbox", "value": "2"}
      ],
      "location": {
        "city": "Vitry-sur-Seine",
        "department_id": "94",
        "lat": 48.787,
        "lng": 2.392
      },
      "owner": {"type": "pro", "name": "Garage Central"},
      "url": "https://www.leboncoin.fr/voitures/12345.htm",
      "body": "Toyota iQ automatique, bon etat, CT OK",
      "images": {"urls": ["https://img.lbc.fr/1.jpg"]}
    },
    {
      "list_id": 67890,
      "subject": "Toyota IQ Manuelle",
      "price": [2500],
      "attributes": [
        {"key": "mileage", "value": "95000"},
        {"key": "regdate", "value": "2010"},
        {"key": "gearbox", "value": "1"}
      ],
      "location": {
        "city": "Paris",
        "department_id": "75",
        "lat": 48.856,
        "lng": 2.352
      },
      "owner": {"type": "private"},
      "url": "https://www.leboncoin.fr/voitures/67890.htm",
      "body": "Vends iQ manuelle",
      "images": {"urls": []}
    }
  ],
  "total": 2
}
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_scraper_lbc.py
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from scraper_lbc import parse_lbc_listings, scrape_leboncoin
from models import RawListing

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "lbc_sample.json")

def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def test_parse_lbc_listings():
    data = load_fixture()
    listings = parse_lbc_listings(data["ads"])
    assert len(listings) == 2
    assert all(isinstance(l, RawListing) for l in listings)
    assert listings[0].id == "lbc_12345"
    assert listings[0].platform == "leboncoin"
    assert listings[0].price == 3200
    assert listings[0].seller_type == "pro"

def test_parse_lbc_extracts_gearbox():
    data = load_fixture()
    listings = parse_lbc_listings(data["ads"])
    assert listings[0].transmission == "auto"  # gearbox=2
    assert listings[1].transmission == "manual"  # gearbox=1

def test_parse_lbc_handles_missing_fields():
    ads = [{"list_id": 999, "subject": "Test", "price": [1000],
            "attributes": [], "location": {}, "owner": {},
            "url": "http://x", "body": "", "images": {}}]
    listings = parse_lbc_listings(ads)
    assert len(listings) == 1
    assert listings[0].mileage_km is None

@patch("scraper_lbc.requests.Session")
def test_scrape_leboncoin_returns_listings(mock_session_cls):
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = load_fixture()
    mock_resp.raise_for_status = MagicMock()
    mock_session.get.return_value = mock_resp
    mock_session_cls.return_value = mock_session

    listings = scrape_leboncoin()
    assert len(listings) >= 1
    assert all(isinstance(l, RawListing) for l in listings)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_scraper_lbc.py -v`
Expected: FAIL

- [ ] **Step 4: Implement scraper_lbc.py**

```python
# scraper_lbc.py
"""LeBonCoin scraper with API + fallback chain."""
import logging
import random
import time
from datetime import datetime, timezone

import requests

from config import SEARCH_CRITERIA
from models import RawListing

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
]

LBC_API_URL = "https://api.leboncoin.fr/finder/search"
LBC_GEARBOX_MAP = {"1": "manual", "2": "auto"}


def _build_lbc_params() -> dict:
    """Build LBC API search parameters."""
    return {
        "category": "2",  # Voitures
        "text": f"{SEARCH_CRITERIA['make']} {SEARCH_CRITERIA['model']}",
        "price": {"min": 0, "max": SEARCH_CRITERIA["max_price"]},
        "mileage": {"min": 0, "max": SEARCH_CRITERIA["max_mileage_km"]},
        "vehicle_vdate": {"min": SEARCH_CRITERIA["min_year"]},
        "limit": 100,
        "offset": 0,
    }


def _get_session() -> requests.Session:
    """Create a session with realistic headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "fr-FR,fr;q=0.9",
    })
    return session


def parse_lbc_listings(ads: list[dict]) -> list[RawListing]:
    """Parse LBC API ad objects into RawListing models."""
    listings = []
    now = datetime.now(timezone.utc).isoformat()

    for ad in ads:
        try:
            attrs = {a["key"]: a.get("value") for a in ad.get("attributes", [])}
            location = ad.get("location", {})
            owner = ad.get("owner", {})
            images_data = ad.get("images", {})
            image_urls = images_data.get("urls", []) if isinstance(images_data, dict) else []

            gearbox_raw = attrs.get("gearbox", "")
            transmission = LBC_GEARBOX_MAP.get(str(gearbox_raw))

            mileage = attrs.get("mileage")
            mileage_km = int(mileage) if mileage else None

            year_raw = attrs.get("regdate")
            year = int(year_raw) if year_raw else 2009

            price_list = ad.get("price", [0])
            price = price_list[0] if price_list else 0

            seller_type = "pro" if owner.get("type") == "pro" else "private"

            listing = RawListing(
                id=f"lbc_{ad['list_id']}",
                platform="leboncoin",
                title=ad.get("subject", ""),
                price=price,
                year=year,
                mileage_km=mileage_km,
                transmission=transmission,
                fuel=attrs.get("fuel"),
                city=location.get("city"),
                department=location.get("department_id"),
                lat=location.get("lat"),
                lon=location.get("lng"),
                seller_type=seller_type,
                url=ad.get("url", ""),
                description=ad.get("body"),
                images=image_urls,
                scraped_at=now,
            )
            listings.append(listing)
        except Exception as e:
            logger.warning(f"Failed to parse LBC ad {ad.get('list_id', '?')}: {e}")

    return listings


def scrape_leboncoin() -> list[RawListing]:
    """Scrape LeBonCoin for Toyota iQ listings. Returns list of RawListing."""
    session = _get_session()
    all_listings = []

    try:
        params = _build_lbc_params()
        time.sleep(random.uniform(2, 5))

        resp = session.get(LBC_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        ads = data.get("ads", [])
        all_listings = parse_lbc_listings(ads)
        logger.info(f"LBC: scraped {len(all_listings)} listings")

        # Handle pagination
        total = data.get("total", 0)
        offset = len(ads)
        while offset < total:
            time.sleep(random.uniform(2, 5))
            params["offset"] = offset
            resp = session.get(LBC_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            page_data = resp.json()
            page_ads = page_data.get("ads", [])
            if not page_ads:
                break
            all_listings.extend(parse_lbc_listings(page_ads))
            offset += len(page_ads)

    except requests.exceptions.HTTPError as e:
        if e.response and e.response.status_code in (403, 429):
            logger.warning(f"LBC blocked ({e.response.status_code}), trying fallback")
            all_listings = _scrape_lbc_fallback(session)
        else:
            logger.error(f"LBC HTTP error: {e}")
    except Exception as e:
        logger.error(f"LBC scrape failed: {e}")

    return all_listings


def _scrape_lbc_fallback(session: requests.Session) -> list[RawListing]:
    """Fallback: scrape LBC via HTML / __NEXT_DATA__ JSON."""
    logger.info("LBC fallback: attempting HTML scrape")
    # Stub — implement HTML parsing if API is blocked
    # For now, return empty and log warning
    logger.warning("LBC HTML fallback not yet implemented")
    return []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_scraper_lbc.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add scraper_lbc.py tests/test_scraper_lbc.py tests/fixtures/lbc_sample.json
git commit -m "feat: LeBonCoin scraper with API + fallback chain"
```

---

### Task 7: La Centrale Scraper

**Files:**
- Create: `scraper_lacentrale.py`
- Create: `tests/fixtures/lacentrale_sample.html`
- Test: `tests/test_scraper_lacentrale.py`

- [ ] **Step 1: Create test fixture**

Create `tests/fixtures/lacentrale_sample.html` — a minimal HTML snippet mimicking La Centrale search results with a `__NEXT_DATA__` JSON block containing 1 listing.

```html
<!-- tests/fixtures/lacentrale_sample.html -->
<html>
<body>
<script id="__NEXT_DATA__" type="application/json">
{
  "props": {
    "pageProps": {
      "searchData": {
        "listings": [
          {
            "id": 98765,
            "title": "TOYOTA IQ 1.33 CVT Multidrive",
            "price": 2900,
            "year": 2012,
            "mileage": 65000,
            "fuel": "Essence",
            "gearbox": "Automatique",
            "city": "Creteil",
            "department": "94",
            "sellerType": "PRO",
            "url": "/auto-occasion-annonce-98765.html",
            "images": ["https://img.lacentrale.fr/1.jpg"]
          }
        ]
      }
    }
  }
}
</script>
</body>
</html>
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_scraper_lacentrale.py
import os
import pytest
from unittest.mock import patch, MagicMock
from scraper_lacentrale import parse_lacentrale_nextdata, scrape_lacentrale
from models import RawListing

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "lacentrale_sample.html")

def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return f.read()

def test_parse_nextdata():
    html = load_fixture()
    listings = parse_lacentrale_nextdata(html)
    assert len(listings) == 1
    assert listings[0].id == "lc_98765"
    assert listings[0].platform == "lacentrale"
    assert listings[0].price == 2900
    assert listings[0].transmission == "auto"
    assert listings[0].seller_type == "pro"

def test_parse_nextdata_empty():
    html = "<html><body></body></html>"
    listings = parse_lacentrale_nextdata(html)
    assert listings == []

@patch("scraper_lacentrale.requests.Session")
@patch("scraper_lacentrale.geocode_city")
def test_scrape_lacentrale(mock_geocode, mock_session_cls):
    mock_geocode.return_value = (48.79, 2.46)
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = load_fixture()
    mock_resp.raise_for_status = MagicMock()
    mock_session.get.return_value = mock_resp
    mock_session_cls.return_value = mock_session

    listings = scrape_lacentrale()
    assert len(listings) >= 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_scraper_lacentrale.py -v`
Expected: FAIL

- [ ] **Step 4: Implement scraper_lacentrale.py**

```python
# scraper_lacentrale.py
"""La Centrale scraper with __NEXT_DATA__ JSON extraction + HTML fallback."""
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import SEARCH_CRITERIA, OUTPUT_DIR
from models import RawListing

logger = logging.getLogger(__name__)

LC_BASE_URL = "https://www.lacentrale.fr/listing"

# Hardcoded geocode cache for common IDF cities
CITY_COORDS_CACHE = {
    "paris": (48.8566, 2.3522), "creteil": (48.7904, 2.4628),
    "vitry-sur-seine": (48.7874, 2.3928), "ivry-sur-seine": (48.8113, 2.3842),
    "villejuif": (48.7922, 2.3637), "orly": (48.7262, 2.3652),
    "antony": (48.7533, 2.2981), "boulogne-billancourt": (48.8397, 2.2399),
    "nanterre": (48.8924, 2.2071), "versailles": (48.8014, 2.1301),
    "evry": (48.6243, 2.4407), "meaux": (48.9601, 2.8788),
    "lyon": (45.7640, 4.8357), "marseille": (43.2965, 5.3698),
    "toulouse": (43.6047, 1.4442), "bordeaux": (44.8378, -0.5792),
    "lille": (50.6292, 3.0573), "nantes": (47.2184, -1.5536),
    "strasbourg": (48.5734, 7.7521), "rennes": (48.1173, -1.6778),
    "montpellier": (43.6108, 3.8767), "nice": (43.7102, 7.2620),
}


def geocode_city(city: str) -> tuple[float, float] | None:
    """Get GPS coordinates for a city. Cache -> Nominatim fallback."""
    if not city:
        return None

    normalized = city.lower().strip()
    if normalized in CITY_COORDS_CACHE:
        return CITY_COORDS_CACHE[normalized]

    # Check disk cache
    cache_path = Path(OUTPUT_DIR) / "geocode_cache.json"
    disk_cache = {}
    if cache_path.exists():
        try:
            disk_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    if normalized in disk_cache:
        coords = disk_cache[normalized]
        return (coords[0], coords[1])

    # Nominatim fallback
    try:
        time.sleep(1.1)  # Nominatim TOS: 1 req/sec
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{city}, France", "format": "json", "limit": 1},
            headers={"User-Agent": "ToyotaIQSearch/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
            disk_cache[normalized] = [lat, lon]
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(disk_cache, indent=2), encoding="utf-8")
            return (lat, lon)
    except Exception as e:
        logger.warning(f"Nominatim geocode failed for {city}: {e}")

    return None


def parse_lacentrale_nextdata(html: str) -> list[RawListing]:
    """Parse La Centrale __NEXT_DATA__ JSON from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        return []

    try:
        data = json.loads(script_tag.string)
        raw_listings_data = (
            data.get("props", {})
            .get("pageProps", {})
            .get("searchData", {})
            .get("listings", [])
        )
    except (json.JSONDecodeError, AttributeError):
        return []

    listings = []
    now = datetime.now(timezone.utc).isoformat()

    for item in raw_listings_data:
        try:
            gearbox = (item.get("gearbox") or "").lower()
            transmission = "auto" if "auto" in gearbox else ("manual" if gearbox else None)

            seller_raw = (item.get("sellerType") or "").upper()
            seller_type = "pro" if "PRO" in seller_raw else "private"

            city = item.get("city", "")
            coords = geocode_city(city)
            lat = coords[0] if coords else None
            lon = coords[1] if coords else None

            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = f"https://www.lacentrale.fr{url}"

            listing = RawListing(
                id=f"lc_{item['id']}",
                platform="lacentrale",
                title=item.get("title", ""),
                price=int(item.get("price", 0)),
                year=int(item.get("year", 2009)),
                mileage_km=int(item["mileage"]) if item.get("mileage") else None,
                transmission=transmission,
                fuel=item.get("fuel"),
                city=city,
                department=item.get("department"),
                lat=lat,
                lon=lon,
                seller_type=seller_type,
                url=url,
                description=None,
                images=item.get("images", []),
                scraped_at=now,
            )
            listings.append(listing)
        except Exception as e:
            logger.warning(f"Failed to parse LC listing {item.get('id', '?')}: {e}")

    return listings


def scrape_lacentrale() -> list[RawListing]:
    """Scrape La Centrale for Toyota iQ listings."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html",
        "Accept-Language": "fr-FR,fr;q=0.9",
    })

    all_listings = []
    make = SEARCH_CRITERIA["make"].lower()
    model = SEARCH_CRITERIA["model"].lower()

    try:
        time.sleep(random.uniform(2, 5))
        url = f"{LC_BASE_URL}?makesModelsCommercialNames={make}%3A{model}"
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        all_listings = parse_lacentrale_nextdata(resp.text)
        logger.info(f"La Centrale: scraped {len(all_listings)} listings")
    except Exception as e:
        logger.error(f"La Centrale scrape failed: {e}")

    return all_listings
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_scraper_lacentrale.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add scraper_lacentrale.py tests/test_scraper_lacentrale.py tests/fixtures/lacentrale_sample.html
git commit -m "feat: La Centrale scraper with geocoding"
```

---

## Chunk 3: Agents & Integration (Tasks 8-12)

### Task 8: Analyst Agent

**Files:**
- Create: `agent_analyst.py`
- Test: `tests/test_analyst.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analyst.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from agent_analyst import analyze_listings, _build_analyst_prompt
from models import RawListing, ScoredListing
from llm_client import LLMResponse

def _make_listing(**overrides):
    defaults = dict(
        id="lbc_1", platform="leboncoin", title="Toyota iQ 1.33 CVT",
        price=3200, year=2011, mileage_km=78000, transmission="auto",
        seller_type="pro", url="http://x", city="Vitry-sur-Seine",
        lat=48.787, lon=2.392, scraped_at=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return RawListing(**defaults)

def test_build_analyst_prompt():
    listings = [_make_listing()]
    prompt = _build_analyst_prompt(listings)
    assert "Toyota iQ" in prompt
    assert "lbc_1" in prompt
    assert "scoring rubric" in prompt.lower() or "SCORING" in prompt

def test_analyze_listings_returns_two_lists():
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text='[{"id":"lbc_1","score":78,"score_breakdown":{"price":25,"mileage":15,"year":10,"proximity":8,"condition":10,"transmission":10},"excluded":false,"exclusion_reason":null,"red_flags":[],"highlights":["CT OK"],"concerns":[],"summary_fr":"Bon etat"}]',
        model_used="ollama",
        raw=None,
    )
    listings = [_make_listing()]
    pro, part = analyze_listings(listings, mock_client)
    assert len(pro) == 1
    assert len(part) == 0
    assert isinstance(pro[0], ScoredListing)
    assert pro[0].score == 78

def test_analyze_listings_splits_pro_and_private():
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text='[{"id":"lbc_1","score":78,"score_breakdown":{"price":25,"mileage":15,"year":10,"proximity":8,"condition":10,"transmission":10},"excluded":false,"exclusion_reason":null,"red_flags":[],"highlights":[],"concerns":[],"summary_fr":"OK"},{"id":"lbc_2","score":65,"score_breakdown":{"price":20,"mileage":10,"year":10,"proximity":15,"condition":5,"transmission":10},"excluded":false,"exclusion_reason":null,"red_flags":[],"highlights":[],"concerns":[],"summary_fr":"OK"}]',
        model_used="ollama",
        raw=None,
    )
    listings = [
        _make_listing(id="lbc_1", seller_type="pro"),
        _make_listing(id="lbc_2", seller_type="private"),
    ]
    pro, part = analyze_listings(listings, mock_client)
    assert len(pro) == 1
    assert len(part) == 1
    assert pro[0].id == "lbc_1"
    assert part[0].id == "lbc_2"

def test_analyze_excludes_manual():
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text='[{"id":"lbc_1","score":-1,"score_breakdown":{"price":0,"mileage":0,"year":0,"proximity":0,"condition":0,"transmission":-100},"excluded":true,"exclusion_reason":"Manual transmission","red_flags":["manual"],"highlights":[],"concerns":[],"summary_fr":"Exclue"}]',
        model_used="ollama",
        raw=None,
    )
    listings = [_make_listing(transmission="manual")]
    pro, part = analyze_listings(listings, mock_client)
    assert len(pro) == 0
    assert len(part) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_analyst.py -v`
Expected: FAIL

- [ ] **Step 3: Implement agent_analyst.py**

```python
# agent_analyst.py
"""Analyst agent: scores listings against weighted rubric via LLM."""
import json
import logging
from models import RawListing, ScoredListing, ScoreBreakdown
from llm_client import LLMClient
from utils import extract_json_from_text

logger = logging.getLogger(__name__)

ANALYST_SYSTEM_PROMPT = """You are a used car analyst specializing in the French market.

TASK: Score each Toyota iQ listing against the buyer's criteria.
Output a JSON ARRAY of objects, one per listing, with the exact schema below.

SCORING RUBRIC (100 points total):
- Price (30 pts): 5000€=0, 4000€=15, 3000€=25, <2500€=30
- Mileage (20 pts): 150k=0, 100k=10, 70k=15, <50k=20
- Year (15 pts): 2009=5, 2011=10, 2013+=15
- Proximity to Orly (15 pts): <20km=15, 20-30km=8, 30-40km=3, >40km=0
- Condition signals (10 pts, CAPPED at 10): "en l'etat"=-10, "accident"=-10, "CT OK"=+5, "carnet entretien"=+5, "1 proprietaire"=+5
- Transmission confirmed auto (10 pts): confirmed=10, unclear=0, manual=EXCLUDE

RED FLAGS (instant exclude or heavy penalty):
- Transmission = manual → EXCLUDE (score = -1)
- Price > 5000€ → EXCLUDE
- Mileage > 150000 km → EXCLUDE
- "en l'etat" / "accidente" / "pour pieces" → score = max 20
- "SIV" / fleet vehicle → -10 pts

OUTPUT SCHEMA (strict JSON array, no markdown, no explanation):
[{
  "id": "lbc_123456",
  "score": 72,
  "score_breakdown": {"price": 25, "mileage": 15, "year": 10, "proximity": 8, "condition": 10, "transmission": 10},
  "excluded": false,
  "exclusion_reason": null,
  "red_flags": [],
  "highlights": ["CT OK", "1 proprio"],
  "concerns": ["km eleve pour l'annee"],
  "summary_fr": "iQ 2011 68k km, bon etat, CT OK."
}]

IMPORTANT: Return ONLY a JSON array. No other text."""


def _build_analyst_prompt(listings: list[RawListing]) -> str:
    """Build the user prompt with listing data."""
    listings_data = []
    for l in listings:
        listings_data.append({
            "id": l.id,
            "title": l.title,
            "price": l.price,
            "year": l.year,
            "mileage_km": l.mileage_km,
            "transmission": l.transmission,
            "city": l.city,
            "lat": l.lat,
            "lon": l.lon,
            "seller_type": l.seller_type,
            "description": l.description,
        })

    return f"""Score these {len(listings)} Toyota iQ listings using the scoring rubric.
Orly coordinates: 48.7262, 2.3652.

LISTINGS:
{json.dumps(listings_data, ensure_ascii=False, indent=2)}

Return a JSON array with one scored object per listing."""


def analyze_listings(
    listings: list[RawListing],
    client: LLMClient,
    top_n: int = 10,
) -> tuple[list[ScoredListing], list[ScoredListing]]:
    """Score listings via LLM, return (shortlist_pro, shortlist_part)."""
    if not listings:
        return [], []

    prompt = _build_analyst_prompt(listings)
    response = client.query(
        messages=[{"role": "user", "content": prompt}],
        model_preference="local",
        system=ANALYST_SYSTEM_PROMPT,
    )

    scored_data = extract_json_from_text(response.text)
    if not scored_data or not isinstance(scored_data, list):
        logger.error(f"Analyst returned invalid JSON: {response.text[:200]}")
        return [], []

    # Build lookup for seller_type from original listings
    seller_lookup = {l.id: l.seller_type for l in listings}
    raw_lookup = {l.id: l for l in listings}

    scored_listings = []
    for item in scored_data:
        try:
            raw = raw_lookup.get(item["id"])
            if not raw:
                continue

            breakdown = ScoreBreakdown(**item["score_breakdown"])
            scored = ScoredListing(
                **raw.model_dump(),
                score=item["score"],
                score_breakdown=breakdown,
                excluded=item.get("excluded", False),
                exclusion_reason=item.get("exclusion_reason"),
                red_flags=item.get("red_flags", []),
                highlights=item.get("highlights", []),
                concerns=item.get("concerns", []),
                summary_fr=item.get("summary_fr", ""),
            )
            scored_listings.append(scored)
        except Exception as e:
            logger.warning(f"Failed to parse scored listing {item.get('id', '?')}: {e}")

    # Filter excluded, split by seller type, sort by score
    active = [s for s in scored_listings if not s.excluded]
    pro = sorted([s for s in active if s.seller_type == "pro"], key=lambda x: x.score, reverse=True)[:top_n]
    part = sorted([s for s in active if s.seller_type != "pro"], key=lambda x: x.score, reverse=True)[:top_n]

    return pro, part
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_analyst.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add agent_analyst.py tests/test_analyst.py
git commit -m "feat: analyst agent with scoring rubric"
```

---

### Task 9: HITL Terminal Interface

**Files:**
- Create: `hitl.py`
- Test: `tests/test_hitl.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_hitl.py
from datetime import datetime, timezone
from unittest.mock import patch
from models import RawListing, ScoredListing, ScoreBreakdown
from hitl import format_listing_line, format_shortlist_display, parse_hitl_command

def _make_scored(id="lbc_1", score=78, seller_type="pro", **kw):
    defaults = dict(
        platform="leboncoin", title="Toyota iQ 1.33 CVT",
        price=3200, year=2011, mileage_km=78000, transmission="auto",
        city="Vitry", lat=48.787, lon=2.392, url="http://x",
        scraped_at=datetime.now(timezone.utc).isoformat(),
        score_breakdown=ScoreBreakdown(price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10),
        excluded=False, red_flags=[], highlights=["CT OK"], concerns=[], summary_fr="OK",
    )
    defaults.update(kw)
    return ScoredListing(id=id, seller_type=seller_type, score=score, **defaults)

def test_format_listing_line():
    s = _make_scored()
    line = format_listing_line(s, 1, distance_km=8.5)
    assert "#1" in line
    assert "78" in line  # score
    assert "3,200" in line or "3200" in line  # price
    assert "Vitry" in line

def test_format_shortlist_display():
    pro = [_make_scored(id="lbc_1", score=80), _make_scored(id="lbc_2", score=70)]
    part = [_make_scored(id="lbc_3", score=75, seller_type="private")]
    output = format_shortlist_display(pro, part, source_counts={"leboncoin": 2, "lacentrale": 1})
    assert "PROFESSIONNELS" in output
    assert "PARTICULIERS" in output
    assert "#1" in output
    assert "#3" in output  # global numbering continues

def test_parse_command_ok_all():
    cmd = parse_hitl_command("ok")
    assert cmd["action"] == "approve_all"

def test_parse_command_ok_specific():
    cmd = parse_hitl_command("ok 1,3,5")
    assert cmd["action"] == "approve"
    assert cmd["numbers"] == [1, 3, 5]

def test_parse_command_drop():
    cmd = parse_hitl_command("drop 2,4")
    assert cmd["action"] == "drop"
    assert cmd["numbers"] == [2, 4]

def test_parse_command_details():
    cmd = parse_hitl_command("details 3")
    assert cmd["action"] == "details"
    assert cmd["number"] == 3

def test_parse_command_rescrape():
    cmd = parse_hitl_command("rescrape")
    assert cmd["action"] == "rescrape"

def test_parse_command_top():
    cmd = parse_hitl_command("top 20")
    assert cmd["action"] == "top"
    assert cmd["n"] == 20

def test_parse_command_quit():
    cmd = parse_hitl_command("quit")
    assert cmd["action"] == "quit"

def test_parse_command_unknown():
    cmd = parse_hitl_command("blablabla")
    assert cmd["action"] == "unknown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_hitl.py -v`
Expected: FAIL

- [ ] **Step 3: Implement hitl.py**

```python
# hitl.py
"""Human-in-the-loop terminal interface for shortlist review."""
import re
from config import ORLY_LAT, ORLY_LON
from models import ScoredListing
from utils import haversine_km


def format_listing_line(listing: ScoredListing, number: int, distance_km: float | None = None) -> str:
    """Format a single listing for terminal display."""
    km_str = f"{listing.mileage_km:,} km" if listing.mileage_km else "km ?"
    price_str = f"{listing.price:,} EUR"
    dist_str = f"({distance_km:.0f} km)" if distance_km is not None else ""
    seller = listing.seller_type.upper() if listing.seller_type else "?"

    highlights = ", ".join(listing.highlights) if listing.highlights else "none"
    flags = ", ".join(listing.red_flags) if listing.red_flags else "none"

    lines = [
        f" #{number} [{listing.score}/100] {listing.year} {listing.title} -- {km_str} -- {price_str}",
        f"    {listing.city} {dist_str} | {seller}",
        f"    + {highlights} | Flags: {flags}",
        f"    {listing.url}",
    ]
    return "\n".join(lines)


def format_shortlist_display(
    pro: list[ScoredListing],
    part: list[ScoredListing],
    source_counts: dict[str, int] | None = None,
    scraped_at: str | None = None,
) -> str:
    """Format the full shortlist display for terminal."""
    lines = []
    total_filtered = len(pro) + len(part)
    src = source_counts or {}
    src_str = ", ".join(f"{k}({v})" for k, v in src.items()) if src else "?"

    lines.append("=" * 55)
    lines.append("  TOYOTA iQ AUTO -- SHORTLIST REVIEW")
    if scraped_at:
        lines.append(f"  Scraped: {scraped_at} | Sources: {src_str}")
    lines.append(f"  Showing: {total_filtered} listings")
    lines.append("=" * 55)

    # Pro listings
    lines.append("")
    lines.append(f"-- PROFESSIONNELS ({len(pro)}) " + "-" * 30)
    lines.append("")
    number = 1
    for s in pro:
        dist = _calc_distance(s)
        lines.append(format_listing_line(s, number, dist))
        lines.append("")
        number += 1

    # Particulier listings (numbering continues)
    lines.append(f"-- PARTICULIERS ({len(part)}) " + "-" * 30)
    lines.append("")
    for s in part:
        dist = _calc_distance(s)
        lines.append(format_listing_line(s, number, dist))
        lines.append("")
        number += 1

    lines.append("=" * 55)
    lines.append("COMMANDS:")
    lines.append("  ok          -> approve all, proceed to pricing")
    lines.append("  ok 1,3,7    -> approve only these numbers")
    lines.append("  drop 2,4    -> remove these numbers")
    lines.append("  details N   -> show full description")
    lines.append("  rescrape    -> re-run scrapers")
    lines.append("  top N       -> change shortlist size")
    lines.append("  quit        -> exit")
    lines.append("=" * 55)

    return "\n".join(lines)


def parse_hitl_command(user_input: str) -> dict:
    """Parse user command from terminal input."""
    text = user_input.strip().lower()

    if text == "ok":
        return {"action": "approve_all"}

    if text.startswith("ok "):
        nums = _parse_numbers(text[3:])
        return {"action": "approve", "numbers": nums}

    if text.startswith("drop "):
        nums = _parse_numbers(text[5:])
        return {"action": "drop", "numbers": nums}

    if text.startswith("details "):
        try:
            n = int(text.split()[1])
            return {"action": "details", "number": n}
        except (ValueError, IndexError):
            return {"action": "unknown"}

    if text == "rescrape":
        return {"action": "rescrape"}

    if text.startswith("top "):
        try:
            n = int(text.split()[1])
            return {"action": "top", "n": n}
        except (ValueError, IndexError):
            return {"action": "unknown"}

    if text == "quit":
        return {"action": "quit"}

    return {"action": "unknown"}


def _parse_numbers(text: str) -> list[int]:
    """Parse comma-separated numbers from text."""
    return [int(x.strip()) for x in text.split(",") if x.strip().isdigit()]


def _calc_distance(listing: ScoredListing) -> float | None:
    """Calculate distance from Orly if GPS coordinates available."""
    if listing.lat is not None and listing.lon is not None:
        return haversine_km(ORLY_LAT, ORLY_LON, listing.lat, listing.lon)
    return None


def run_hitl_review(
    pro: list[ScoredListing],
    part: list[ScoredListing],
    source_counts: dict[str, int] | None = None,
) -> dict:
    """Interactive HITL review loop. Returns command dict with approved IDs."""
    display = format_shortlist_display(pro, part, source_counts)
    print(display)

    all_listings = pro + part  # global numbering: pro first, then part

    while True:
        try:
            user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            return {"action": "quit"}

        cmd = parse_hitl_command(user_input)

        if cmd["action"] == "approve_all":
            return {"action": "approve", "approved_ids": [l.id for l in all_listings]}

        elif cmd["action"] == "approve":
            ids = []
            for n in cmd["numbers"]:
                idx = n - 1
                if 0 <= idx < len(all_listings):
                    ids.append(all_listings[idx].id)
            return {"action": "approve", "approved_ids": ids}

        elif cmd["action"] == "drop":
            for n in sorted(cmd["numbers"], reverse=True):
                idx = n - 1
                if 0 <= idx < len(all_listings):
                    all_listings.pop(idx)
            # Re-display
            new_pro = [l for l in all_listings if l.seller_type == "pro"]
            new_part = [l for l in all_listings if l.seller_type != "pro"]
            display = format_shortlist_display(new_pro, new_part, source_counts)
            print(display)

        elif cmd["action"] == "details":
            idx = cmd["number"] - 1
            if 0 <= idx < len(all_listings):
                l = all_listings[idx]
                print(f"\n--- Details #{cmd['number']} ---")
                print(f"Title: {l.title}")
                print(f"Description: {l.description or 'N/A'}")
                print(f"Summary: {l.summary_fr}")
                print(f"Score breakdown: {l.score_breakdown.model_dump()}")
                print(f"URL: {l.url}")
                print("---\n")

        elif cmd["action"] == "rescrape":
            return {"action": "rescrape"}

        elif cmd["action"] == "top":
            return {"action": "top", "n": cmd["n"]}

        elif cmd["action"] == "quit":
            return {"action": "quit"}

        else:
            print("Unknown command. Type 'ok', 'ok 1,3', 'drop 2', 'details 3', 'rescrape', 'top N', or 'quit'.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_hitl.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add hitl.py tests/test_hitl.py
git commit -m "feat: HITL terminal interface"
```

---

### Task 10: Pricer Agent

**Files:**
- Create: `agent_pricer.py`
- Test: `tests/test_pricer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pricer.py
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
from agent_pricer import price_listings, _build_pricer_prompt
from models import ScoredListing, ScoreBreakdown, PricedListing
from llm_client import LLMResponse

def _make_scored(**kw):
    defaults = dict(
        id="lbc_1", platform="leboncoin", title="Toyota iQ 1.33 CVT",
        price=3200, year=2011, mileage_km=78000, transmission="auto",
        seller_type="pro", url="http://x", city="Vitry",
        scraped_at=datetime.now(timezone.utc).isoformat(),
        score=78,
        score_breakdown=ScoreBreakdown(price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10),
        excluded=False, red_flags=[], highlights=["CT OK"], concerns=[], summary_fr="OK",
    )
    defaults.update(kw)
    return ScoredListing(**defaults)

def test_build_pricer_prompt():
    listings = [_make_scored()]
    prompt = _build_pricer_prompt(listings)
    assert "lbc_1" in prompt
    assert "negociation" in prompt.lower() or "negotiation" in prompt.lower()

def test_price_listings_returns_priced():
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text='[{"id":"lbc_1","market_estimate_low":2500,"market_estimate_high":3200,"opening_offer":2400,"max_acceptable":3000,"anchors":["km eleve"],"message_digital":"Bonjour...","message_oral_points":["Mentionner km"]}]',
        model_used="claude-sonnet-4-20250514",
        raw=None,
    )
    scored = [_make_scored()]
    result = price_listings(scored, mock_client)
    assert len(result) == 1
    assert isinstance(result[0], PricedListing)
    assert result[0].opening_offer == 2400
    assert result[0].market_estimate_low == 2500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_pricer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement agent_pricer.py**

```python
# agent_pricer.py
"""Pricer agent: market pricing + negotiation message generation via Claude Sonnet."""
import json
import logging
from models import ScoredListing, PricedListing
from llm_client import LLMClient
from utils import extract_json_from_text

logger = logging.getLogger(__name__)

PRICER_SYSTEM_PROMPT = """You are a French used car negotiation expert.

For each approved listing, produce:
1. Market price estimate (fourchette basse/haute) based on year, km, condition
2. Recommended opening offer (aggressive but not insulting)
3. Maximum acceptable price (walk-away point)
4. Negotiation anchors: specific weak points to leverage (km, age, condition, market rarity)
5. A ready-to-send message in French (vouvoiement, polite but informed)
   - For digital platforms (LBC message, email)
6. Oral talking points for phone/in-person

TONE: Informed buyer, respectful, not desperate. Reference specific facts about the car.
Never insult the seller or the car. Use "je me permets de vous proposer" style.

OUTPUT SCHEMA (strict JSON array, no markdown):
[{
  "id": "lbc_123456",
  "market_estimate_low": 2500,
  "market_estimate_high": 3200,
  "opening_offer": 2400,
  "max_acceptable": 3000,
  "anchors": ["Kilometrage superieur a la moyenne", "CT a refaire"],
  "message_digital": "Bonjour, je me permets de vous contacter...",
  "message_oral_points": ["Mentionner le kilometrage", "Demander le carnet"]
}]

IMPORTANT: Return ONLY a JSON array. No other text."""


def _build_pricer_prompt(listings: list[ScoredListing]) -> str:
    """Build the user prompt with listing data for pricing."""
    data = []
    for l in listings:
        data.append({
            "id": l.id,
            "title": l.title,
            "price": l.price,
            "year": l.year,
            "mileage_km": l.mileage_km,
            "city": l.city,
            "seller_type": l.seller_type,
            "score": l.score,
            "highlights": l.highlights,
            "concerns": l.concerns,
            "red_flags": l.red_flags,
            "description": l.description,
        })

    return f"""Price these {len(listings)} approved Toyota iQ listings and generate negotiation strategies.

LISTINGS:
{json.dumps(data, ensure_ascii=False, indent=2)}

Return a JSON array with pricing and negotiation data for each listing."""


def price_listings(
    listings: list[ScoredListing],
    client: LLMClient,
) -> list[PricedListing]:
    """Price approved listings via Claude Sonnet."""
    if not listings:
        return []

    prompt = _build_pricer_prompt(listings)
    response = client.query(
        messages=[{"role": "user", "content": prompt}],
        model_preference="sonnet",
        system=PRICER_SYSTEM_PROMPT,
    )

    priced_data = extract_json_from_text(response.text)
    if not priced_data or not isinstance(priced_data, list):
        logger.error(f"Pricer returned invalid JSON: {response.text[:200]}")
        return []

    # Build lookup
    scored_lookup = {l.id: l for l in listings}

    priced_listings = []
    for item in priced_data:
        try:
            scored = scored_lookup.get(item["id"])
            if not scored:
                continue

            priced = PricedListing(
                **scored.model_dump(),
                market_estimate_low=item["market_estimate_low"],
                market_estimate_high=item["market_estimate_high"],
                opening_offer=item["opening_offer"],
                max_acceptable=item["max_acceptable"],
                anchors=item.get("anchors", []),
                message_digital=item.get("message_digital", ""),
                message_oral_points=item.get("message_oral_points", []),
            )
            priced_listings.append(priced)
        except Exception as e:
            logger.warning(f"Failed to parse priced listing {item.get('id', '?')}: {e}")

    return priced_listings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_pricer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add agent_pricer.py tests/test_pricer.py
git commit -m "feat: pricer agent with negotiation messages"
```

---

### Task 11: Supervisor Agent

**Files:**
- Create: `agent_supervisor.py`
- Test: `tests/test_supervisor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_supervisor.py
import pytest
from unittest.mock import MagicMock, patch
from agent_supervisor import (
    SUPERVISOR_TOOLS, build_supervisor_system_prompt,
    execute_tool, SupervisorAgent,
)

def test_supervisor_tools_defined():
    assert len(SUPERVISOR_TOOLS) == 7
    tool_names = [t["name"] for t in SUPERVISOR_TOOLS]
    assert "scrape_platforms" in tool_names
    assert "get_raw_listings" in tool_names
    assert "dispatch_analyst" in tool_names
    assert "dispatch_pricer" in tool_names
    assert "ask_human" in tool_names
    assert "read_state" in tool_names
    assert "write_state" in tool_names

def test_system_prompt_contains_mission():
    prompt = build_supervisor_system_prompt()
    assert "Toyota iQ" in prompt
    assert "automatic" in prompt.lower() or "automatique" in prompt.lower()

def test_execute_tool_read_state():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state_path = "fake_path"
    with patch("agent_supervisor.load_state") as mock_load:
        mock_state = MagicMock()
        mock_state.model_dump_json.return_value = '{"step":"init"}'
        mock_load.return_value = mock_state
        result = execute_tool("read_state", {}, agent)
        assert "init" in result

def test_supervisor_agent_init():
    with patch("agent_supervisor.load_state") as mock_load, \
         patch("agent_supervisor.LLMClient"):
        mock_load.return_value = MagicMock()
        agent = SupervisorAgent(state_path="test_state.json")
        assert agent is not None

def test_ask_human_uses_hitl_when_shortlists_present():
    """When shortlists exist, ask_human should use run_hitl_review, not raw input."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = [MagicMock()]
    agent._shortlist_part = []
    agent._raw_listings = [MagicMock(platform="leboncoin")]
    with patch("agent_supervisor.run_hitl_review") as mock_hitl:
        mock_hitl.return_value = {"action": "approve", "approved_ids": ["lbc_1"]}
        result = execute_tool("ask_human", {"question": "Review?"}, agent)
        mock_hitl.assert_called_once()
        assert "approved" in result
        assert "lbc_1" in result

def test_ask_human_falls_back_to_input_without_shortlists():
    """Without shortlists, ask_human uses simple input()."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = []
    agent._shortlist_part = []
    with patch("builtins.input", return_value="yes"):
        result = execute_tool("ask_human", {"question": "Continue?"}, agent)
        assert "yes" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_supervisor.py -v`
Expected: FAIL

- [ ] **Step 3: Implement agent_supervisor.py**

```python
# agent_supervisor.py
"""Supervisor Agent: Claude Sonnet tool_use loop that orchestrates the pipeline."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import CACHE_FRESHNESS_HOURS, OUTPUT_DIR, PLATFORMS
from llm_client import LLMClient
from models import RawListing, ScoredListing
from state import PipelineState, load_state, save_state

logger = logging.getLogger(__name__)


def build_supervisor_system_prompt() -> str:
    return """You are the supervisor of a car search mission for a Toyota iQ automatic.

YOUR MISSION: Find the best Toyota iQ automatic deals in France for a friend.
Budget: max 5000 EUR. Max 150k km. Min 2009. Automatic only.

YOU HAVE TOOLS. Use them. You are in a loop.

WORKFLOW:
1. Call read_state to check current pipeline state.
2. If no fresh data (last scrape > 4 hours), call scrape_platforms.
3. After scraping, call get_raw_listings to see the data.
4. Call dispatch_analyst to score and rank the listings.
5. Call ask_human to present shortlists and get approval.
6. If human approves listings, call dispatch_pricer for approved ones.
7. Present final pricing to human. Done.

DECISION RULES:
- 0 listings after scrape? Tell human via ask_human, suggest retry later.
- 1 platform failed? Continue with partial data, note it.
- Analyst returns bad output? Retry up to 2x with dispatch_analyst.
- Human says "rescrape"? Call scrape_platforms again.
- Human says "top N"? Call dispatch_analyst again with new top_n.
- Human says "quit"? Stop immediately.

NEVER proceed without validating the previous step output.
ALWAYS explain your reasoning before calling a tool."""


SUPERVISOR_TOOLS = [
    {
        "name": "scrape_platforms",
        "description": "Scrape LeBonCoin and La Centrale for Toyota iQ listings. Returns count and status per platform.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Platforms to scrape: 'leboncoin', 'lacentrale'"
                }
            },
            "required": ["platforms"]
        }
    },
    {
        "name": "get_raw_listings",
        "description": "Get the most recent raw listings from cache.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "dispatch_analyst",
        "description": "Send listings to the analyst agent for scoring. Returns two shortlists (pro + private).",
        "input_schema": {
            "type": "object",
            "properties": {
                "top_n": {
                    "type": "integer",
                    "description": "Max listings per shortlist (default 10)"
                }
            }
        }
    },
    {
        "name": "dispatch_pricer",
        "description": "Send approved listings to the pricer agent for market pricing and negotiation messages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "listing_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of approved listings"
                }
            },
            "required": ["listing_ids"]
        }
    },
    {
        "name": "ask_human",
        "description": "Present information to the human and get their response via terminal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "What to ask or show"},
                "context": {"type": "string", "description": "Additional context"}
            },
            "required": ["question"]
        }
    },
    {
        "name": "read_state",
        "description": "Read the current pipeline state.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "write_state",
        "description": "Update the pipeline state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "updates": {"type": "object", "description": "State fields to update"}
            },
            "required": ["updates"]
        }
    },
]


class SupervisorAgent:
    """Supervisor agent: Claude Sonnet in a tool_use loop."""

    def __init__(self, state_path: str | None = None):
        self.llm = LLMClient()
        self.state_path = state_path or str(Path(OUTPUT_DIR) / "state.json")
        self.state = load_state(self.state_path)
        self.messages: list[dict] = []
        self._raw_listings: list[RawListing] = []
        self._shortlist_pro: list[ScoredListing] = []
        self._shortlist_part: list[ScoredListing] = []

    def run(self) -> None:
        """Main supervisor loop."""
        system = build_supervisor_system_prompt()
        self.messages = [
            {"role": "user", "content": "Begin the Toyota iQ automatic search mission. Start by reading the current state."}
        ]

        max_iterations = 20
        for i in range(max_iterations):
            logger.info(f"Supervisor iteration {i+1}")

            response = self.llm.query_with_tools(
                messages=self.messages,
                tools=SUPERVISOR_TOOLS,
                system=system,
            )

            # Process response content
            assistant_content = response["content"]
            self.messages.append({"role": "assistant", "content": assistant_content})

            # Check if supervisor wants to use a tool
            if response["stop_reason"] == "tool_use":
                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        logger.info(f"Supervisor calls tool: {block.name}")
                        result = execute_tool(block.name, block.input, self)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                self.messages.append({"role": "user", "content": tool_results})

            elif response["stop_reason"] == "end_turn":
                # Supervisor decided to stop
                for block in assistant_content:
                    if hasattr(block, "text"):
                        print(f"\n[Supervisor] {block.text}")
                break

        save_state(self.state, self.state_path)
        logger.info("Supervisor loop ended")


def execute_tool(tool_name: str, tool_input: dict, agent: SupervisorAgent) -> str:
    """Execute a supervisor tool and return result as string."""
    try:
        if tool_name == "read_state":
            state = load_state(agent.state_path)
            return state.model_dump_json(indent=2)

        elif tool_name == "write_state":
            updates = tool_input.get("updates", {})
            for k, v in updates.items():
                if hasattr(agent.state, k):
                    setattr(agent.state, k, v)
            save_state(agent.state, agent.state_path)
            return json.dumps({"status": "ok", "updated": list(updates.keys())})

        elif tool_name == "scrape_platforms":
            return _tool_scrape(tool_input, agent)

        elif tool_name == "get_raw_listings":
            return _tool_get_raw(agent)

        elif tool_name == "dispatch_analyst":
            return _tool_analyst(tool_input, agent)

        elif tool_name == "dispatch_pricer":
            return _tool_pricer(tool_input, agent)

        elif tool_name == "ask_human":
            return _tool_ask_human(tool_input, agent)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return json.dumps({"error": str(e)})


def _tool_scrape(tool_input: dict, agent: SupervisorAgent) -> str:
    from scraper_lbc import scrape_leboncoin
    from scraper_lacentrale import scrape_lacentrale

    platforms = tool_input.get("platforms", PLATFORMS)
    results = {"platforms_ok": [], "platforms_failed": [], "total_count": 0}
    all_listings = []

    for p in platforms:
        try:
            if p == "leboncoin":
                listings = scrape_leboncoin()
            elif p == "lacentrale":
                listings = scrape_lacentrale()
            else:
                continue
            all_listings.extend(listings)
            results["platforms_ok"].append(p)
        except Exception as e:
            logger.error(f"Scrape {p} failed: {e}")
            results["platforms_failed"].append(p)

    # Dedup by (title_lower, price, year, city_lower)
    seen = set()
    deduped = []
    for l in all_listings:
        key = (l.title.lower().strip(), l.price, l.year, (l.city or "").lower().strip())
        if key not in seen:
            seen.add(key)
            deduped.append(l)

    agent._raw_listings = deduped
    results["total_count"] = len(deduped)

    # Save raw listings
    output_path = Path(OUTPUT_DIR) / f"raw_listings_{datetime.now().strftime('%Y%m%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([l.model_dump() for l in deduped], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Update state
    agent.state.last_scrape_at = datetime.now(timezone.utc).isoformat()
    agent.state.last_scrape_platforms = results["platforms_ok"]
    agent.state.raw_listing_count = len(deduped)
    agent.state.step = "scraped"
    save_state(agent.state, agent.state_path)

    return json.dumps(results)


def _tool_get_raw(agent: SupervisorAgent) -> str:
    if not agent._raw_listings:
        # Try loading from latest file
        output_dir = Path(OUTPUT_DIR)
        files = sorted(output_dir.glob("raw_listings_*.json"), reverse=True)
        if files:
            data = json.loads(files[0].read_text(encoding="utf-8"))
            agent._raw_listings = [RawListing.model_validate(d) for d in data]

    summary = []
    for l in agent._raw_listings:
        summary.append({
            "id": l.id, "title": l.title, "price": l.price,
            "year": l.year, "mileage_km": l.mileage_km,
            "transmission": l.transmission, "city": l.city,
            "seller_type": l.seller_type,
        })
    return json.dumps({"count": len(summary), "listings": summary}, ensure_ascii=False)


def _tool_analyst(tool_input: dict, agent: SupervisorAgent) -> str:
    from agent_analyst import analyze_listings

    top_n = tool_input.get("top_n", 10)
    if not agent._raw_listings:
        return json.dumps({"error": "No raw listings loaded. Call get_raw_listings first."})

    pro, part = analyze_listings(agent._raw_listings, agent.llm, top_n=top_n)
    agent._shortlist_pro = pro
    agent._shortlist_part = part

    agent.state.analysis_status = "done"
    agent.state.shortlist_pro_count = len(pro)
    agent.state.shortlist_part_count = len(part)
    agent.state.step = "analyzed"
    save_state(agent.state, agent.state_path)

    return json.dumps({
        "shortlist_pro": [{"id": s.id, "score": s.score, "title": s.title, "price": s.price} for s in pro],
        "shortlist_part": [{"id": s.id, "score": s.score, "title": s.title, "price": s.price} for s in part],
    }, ensure_ascii=False)


def _tool_pricer(tool_input: dict, agent: SupervisorAgent) -> str:
    from agent_pricer import price_listings

    listing_ids = tool_input.get("listing_ids", [])
    all_scored = agent._shortlist_pro + agent._shortlist_part
    to_price = [s for s in all_scored if s.id in listing_ids]

    if not to_price:
        return json.dumps({"error": "No matching listings found for the given IDs."})

    priced = price_listings(to_price, agent.llm)

    # Save priced output
    output_path = Path(OUTPUT_DIR) / f"priced_{datetime.now().strftime('%Y%m%d')}.json"
    output_path.write_text(
        json.dumps([p.model_dump() for p in priced], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    agent.state.pricing_status = "done"
    agent.state.step = "priced"
    save_state(agent.state, agent.state_path)

    result = []
    for p in priced:
        result.append({
            "id": p.id, "title": p.title,
            "market_estimate": f"{p.market_estimate_low}-{p.market_estimate_high} EUR",
            "opening_offer": p.opening_offer,
            "max_acceptable": p.max_acceptable,
            "message_digital": p.message_digital[:100] + "...",
        })
    return json.dumps(result, ensure_ascii=False)


def _tool_ask_human(tool_input: dict, agent: SupervisorAgent) -> str:
    from hitl import run_hitl_review, format_shortlist_display

    question = tool_input.get("question", "")
    context = tool_input.get("context", "")

    # If shortlists are available, use the full HITL review interface
    if agent._shortlist_pro or agent._shortlist_part:
        source_counts = {}
        for l in agent._raw_listings:
            source_counts[l.platform] = source_counts.get(l.platform, 0) + 1

        result = run_hitl_review(
            agent._shortlist_pro,
            agent._shortlist_part,
            source_counts=source_counts,
        )

        if result["action"] == "approve":
            return json.dumps({
                "human_response": "approved",
                "approved_ids": result.get("approved_ids", []),
            })
        elif result["action"] == "rescrape":
            return json.dumps({"human_response": "rescrape"})
        elif result["action"] == "top":
            return json.dumps({"human_response": f"top {result['n']}"})
        elif result["action"] == "quit":
            return json.dumps({"human_response": "quit"})
        else:
            return json.dumps({"human_response": str(result)})

    # Fallback: simple question/answer for non-shortlist interactions
    print(f"\n[Supervisor asks]: {question}")
    if context:
        print(f"[Context]: {context}")

    try:
        response = input("> ")
        return json.dumps({"human_response": response})
    except (EOFError, KeyboardInterrupt):
        return json.dumps({"human_response": "quit"})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_supervisor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add agent_supervisor.py tests/test_supervisor.py
git commit -m "feat: supervisor agent with tool_use loop"
```

---

### Task 12: CLI Entry Point

**Files:**
- Create: `run.py`
- Test: `tests/test_run.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_run.py
from unittest.mock import patch, MagicMock
from run import main

def test_main_no_args_runs_supervisor():
    with patch("run.SupervisorAgent") as mock_cls:
        mock_agent = MagicMock()
        mock_cls.return_value = mock_agent
        main(["run.py"])
        mock_agent.run.assert_called_once()

def test_main_scrape_only():
    with patch("run.scrape_leboncoin", return_value=[]) as mock_lbc, \
         patch("run.scrape_lacentrale", return_value=[]) as mock_lc:
        main(["run.py", "scrape"])
        mock_lbc.assert_called_once()
        mock_lc.assert_called_once()

def test_main_status():
    with patch("run.load_state") as mock_load:
        mock_state = MagicMock()
        mock_state.model_dump_json.return_value = '{"step":"init"}'
        mock_load.return_value = mock_state
        main(["run.py", "status"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_run.py -v`
Expected: FAIL

- [ ] **Step 3: Implement run.py**

```python
# run.py
"""CLI entry point for Toyota iQ search pipeline."""
import json
import logging
import sys
from pathlib import Path

from config import OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def main(argv: list[str] | None = None):
    args = argv or sys.argv
    command = args[1] if len(args) > 1 else "run"

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    if command == "run":
        from agent_supervisor import SupervisorAgent
        agent = SupervisorAgent()
        agent.run()

    elif command == "scrape":
        from scraper_lbc import scrape_leboncoin
        from scraper_lacentrale import scrape_lacentrale
        from datetime import datetime

        print("Scraping LeBonCoin...")
        lbc = scrape_leboncoin()
        print(f"  LBC: {len(lbc)} listings")

        print("Scraping La Centrale...")
        lc = scrape_lacentrale()
        print(f"  LC: {len(lc)} listings")

        all_listings = lbc + lc
        output = Path(OUTPUT_DIR) / f"raw_listings_{datetime.now().strftime('%Y%m%d')}.json"
        output.write_text(
            json.dumps([l.model_dump() for l in all_listings], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved {len(all_listings)} listings to {output}")

    elif command == "analyze":
        from agent_analyst import analyze_listings
        from llm_client import LLMClient
        from models import RawListing

        files = sorted(Path(OUTPUT_DIR).glob("raw_listings_*.json"), reverse=True)
        if not files:
            print("No raw listings found. Run 'scrape' first.")
            return
        data = json.loads(files[0].read_text(encoding="utf-8"))
        listings = [RawListing.model_validate(d) for d in data]
        print(f"Loaded {len(listings)} listings from {files[0].name}")

        client = LLMClient()
        pro, part = analyze_listings(listings, client)
        print(f"Shortlist: {len(pro)} pro, {len(part)} particulier")

    elif command == "price":
        from agent_pricer import price_listings
        from llm_client import LLMClient
        from models import ScoredListing

        files = sorted(Path(OUTPUT_DIR).glob("shortlist_approved_*.json"), reverse=True)
        if not files:
            print("No approved shortlist found. Run full pipeline first.")
            return
        data = json.loads(files[0].read_text(encoding="utf-8"))
        listings = [ScoredListing.model_validate(d) for d in data]

        client = LLMClient()
        priced = price_listings(listings, client)
        print(f"Priced {len(priced)} listings")

    elif command == "status":
        from state import load_state
        state = load_state(str(Path(OUTPUT_DIR) / "state.json"))
        print(state.model_dump_json(indent=2))

    else:
        print(f"Unknown command: {command}")
        print("Usage: python run.py [run|scrape|analyze|price|status]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/test_run.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add run.py tests/test_run.py
git commit -m "feat: CLI entry point"
```

---

## Chunk 4: New Platforms + Telegram + Scheduler (Tasks 13-16)

### Task 13: Le Parking Scraper

**Files:**
- Create: `scraper_leparking.py`
- Create: `tests/fixtures/leparking_sample.html`
- Test: `tests/test_scraper_leparking.py`

**Context:** Le Parking is an aggregator site. HTML scraping. May overlap with LBC/LC — dedup in supervisor handles this. Search URL pattern: `https://www.leparking.fr/voiture-occasion/toyota-iq.html`. Listings are in structured HTML divs. Extract: title, price, year, mileage, city, seller type, URL, images.

- [ ] **Step 1: Create test fixture** — minimal HTML mimicking Le Parking search results with 1-2 listings
- [ ] **Step 2: Write failing tests** for `parse_leparking_html()` and `scrape_leparking()`
- [ ] **Step 3: Run tests to verify they fail**
- [ ] **Step 4: Implement scraper_leparking.py** — HTML parse with BeautifulSoup, same RawListing output, anti-detection (delays, UA rotation), geocoding for city names
- [ ] **Step 5: Run tests to verify they pass**
- [ ] **Step 6: Commit**

```bash
git add scraper_leparking.py tests/test_scraper_leparking.py tests/fixtures/leparking_sample.html
git commit -m "feat: Le Parking scraper"
```

---

### Task 14: AutoScout24 Scraper

**Files:**
- Create: `scraper_autoscout.py`
- Create: `tests/fixtures/autoscout_sample.json`
- Test: `tests/test_scraper_autoscout.py`

**Context:** AutoScout24 has a structured search API or Next.js JSON. Search URL: `https://www.autoscout24.fr/lst/toyota/iq`. Extract from JSON/HTML: title, price, year, mileage, transmission, city, GPS (usually available), seller type, URL, images.

- [ ] **Step 1: Create test fixture** — JSON or HTML sample with 1-2 listings
- [ ] **Step 2: Write failing tests** for `parse_autoscout_listings()` and `scrape_autoscout24()`
- [ ] **Step 3: Run tests to verify they fail**
- [ ] **Step 4: Implement scraper_autoscout.py** — JSON extraction preferred, HTML fallback, same RawListing output, anti-detection
- [ ] **Step 5: Run tests to verify they pass**
- [ ] **Step 6: Commit**

```bash
git add scraper_autoscout.py tests/test_scraper_autoscout.py tests/fixtures/autoscout_sample.json
git commit -m "feat: AutoScout24 scraper"
```

---

### Task 15: Telegram Bot

**Files:**
- Create: `telegram_bot.py`
- Test: `tests/test_telegram.py`

**Context:** New dedicated Telegram bot using `python-telegram-bot` v20+ (async). Two chats: FRIEND_CHAT_ID (primary) and JEROME_CHAT_ID (mirror). Bot handles commands and sends notifications. Pipeline results are sent via the notification layer.

**Friend commands:** `/start`, `/search`, `/shortlist`, `/approve 1,3,5`, `/reject 2,4`, `/details 3`, `/interval 4h`, `/status`

**Jerome mirror:** Receives copies of all shortlists, alerts, and error notifications. Same commands available for override.

**New listing alerts:** When a run finds listing IDs not in `state.known_listing_ids`, send formatted alert to both chats.

- [ ] **Step 1: Write failing tests**

Tests should cover:
- `format_listing_telegram(scored_listing, number)` returns formatted text
- `format_shortlist_telegram(pro, part)` returns full display
- `parse_interval("4h")` returns 4, `parse_interval("1d")` returns 24, `parse_interval("1w")` returns 168
- `parse_interval("30m")` returns None (below minimum)
- Command handler registration (verify all commands are registered)

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement telegram_bot.py**

Key implementation:
- `TelegramNotifier` class with `send_to_friend(text)`, `send_to_jerome(text)`, `send_to_both(text)`
- Command handlers: `/start`, `/search`, `/shortlist`, `/approve`, `/reject`, `/details`, `/interval`, `/status`
- `/search` triggers pipeline in background thread
- `/approve` and `/reject` modify approved_ids in state
- `/interval` validates range (1h-1w), updates state, reschedules APScheduler
- `send_new_listing_alert(listing, number)` — formatted alert for new listings
- `format_listing_telegram()` and `format_shortlist_telegram()` — Telegram-formatted text (plain text, no markdown per CLAUDE.md)
- Bot runs via `Application.run_polling()` in the main asyncio loop

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add telegram_bot.py tests/test_telegram.py
git commit -m "feat: Telegram bot with friend + Jerome mirror"
```

---

### Task 16: Scheduler + Updated run.py

**Files:**
- Create: `scheduler.py`
- Modify: `run.py` — add bot + scheduler startup
- Modify: `agent_supervisor.py` — add `notify_telegram` tool, update `scrape_platforms` to include 4 scrapers
- Test: `tests/test_scheduler.py`

**Context:** APScheduler runs the pipeline on a configurable interval (default 4h, range 1h-1w). The scheduler, Telegram bot, and CLI all coexist in the same process. `run.py` is the single entry point.

- [ ] **Step 1: Write failing tests**

Tests for scheduler.py:
- `PipelineScheduler` can be created with default interval
- `update_interval(hours)` changes the interval
- `update_interval(0.5)` rejects below minimum
- `update_interval(200)` rejects above maximum

Tests for updated run.py:
- `main(["run.py"])` starts bot + scheduler (mocked)
- `main(["run.py", "scrape"])` still works standalone
- `main(["run.py", "status"])` still works

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement scheduler.py**

```python
# scheduler.py
"""Configurable pipeline scheduler using APScheduler."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import DEFAULT_INTERVAL_HOURS, MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS

class PipelineScheduler:
    def __init__(self, run_pipeline_fn, interval_hours=DEFAULT_INTERVAL_HOURS):
        self.scheduler = BackgroundScheduler()
        self.run_pipeline_fn = run_pipeline_fn
        self.interval_hours = interval_hours
        self.job = None

    def start(self):
        self.job = self.scheduler.add_job(
            self.run_pipeline_fn,
            trigger=IntervalTrigger(hours=self.interval_hours),
            id="pipeline_run",
            replace_existing=True,
        )
        self.scheduler.start()

    def update_interval(self, hours: float) -> bool:
        if hours < MIN_INTERVAL_HOURS or hours > MAX_INTERVAL_HOURS:
            return False
        self.interval_hours = hours
        if self.job:
            self.job.reschedule(trigger=IntervalTrigger(hours=hours))
        return True

    def stop(self):
        self.scheduler.shutdown(wait=False)
```

- [ ] **Step 4: Update run.py** — main() starts Telegram bot + scheduler when no subcommand given; subcommands (scrape, analyze, price, status) still work standalone
- [ ] **Step 5: Update agent_supervisor.py** — add `notify_telegram` tool, update `_tool_scrape` to dispatch all 4 scrapers, add new listing detection (diff against state.known_listing_ids)
- [ ] **Step 6: Run tests to verify they pass**
- [ ] **Step 7: Run full test suite**

Run: `cd G:/Downloads/_search_vehicles && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add scheduler.py run.py agent_supervisor.py tests/test_scheduler.py
git commit -m "feat: scheduler + Telegram integration + 4-platform scraping"
```

---

## Integration Verification

After all 16 tasks are complete:

- [ ] **Run full test suite:** `python -m pytest tests/ -v`
- [ ] **Verify imports:** `python -c "from run import main; print('OK')"`
- [ ] **Check status command:** `python run.py status`
- [ ] **Check scrape command:** `python run.py scrape` (tests all 4 scrapers)
- [ ] **Final commit:** `git add -A && git commit -m "feat: Toyota iQ agentic search pipeline v2 complete"`
