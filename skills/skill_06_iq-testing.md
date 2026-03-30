---
name: iq-testing
description: Complete test strategy for IQ Auto Search v2 — TDD workflow, pytest structure, fixture conventions, Green/Red gates, and coverage requirements per module. Load for any testing task.
version: 1.0
updated: 2026-03-28
load: test | pytest | TDD | fixture | scraper test | agent test | mock | coverage | green | red
---

# SKILL 06 — TESTING STRATEGY

## Test philosophy

TDD for scrapers and data models (deterministic, can be written before code).
Behavior-driven for agents (prompts change — test output contracts, not internals).
Fixtures = captured real HTML/JSON — no mocking of external HTML structure.

## Structure

```
tests/
├── conftest.py                 # fixtures, shared utils
├── fixtures/
│   ├── lbc_iq_auto_page.html   # captured LBC search result page
│   ├── lbc_iq_listing_detail.html
│   ├── lc_iq_auto_page.html    # captured La Centrale page
│   └── raw_listings_sample.json  # 5 representative listings (2 pro, 2 private, 1 manual=EXCLUDE)
├── test_scraper.py
├── test_analyst.py
├── test_pricer.py
├── test_supervisor.py
└── test_data.py                # Pydantic models, state, utils
```

## conftest.py — key fixtures

```python
import pytest, json
from pathlib import Path

@pytest.fixture
def sample_raw_listings():
    """5 listings: 2 pro auto, 2 private auto, 1 manual (must be excluded)."""
    return json.loads(Path("tests/fixtures/raw_listings_sample.json").read_text())

@pytest.fixture
def single_auto_listing():
    return {"id": "lbc_test_001", "platform": "leboncoin", "title": "Toyota iQ 1.33 Multidrive",
            "price": 3200, "year": 2012, "mileage_km": 52000, "transmission": "auto",
            "city": "Vitry-sur-Seine", "lat": 48.793, "lon": 2.392,
            "seller_type": "pro", "url": "https://lbc.fr/test", "scraped_at": "2026-03-28T10:00:00Z"}

@pytest.fixture
def manual_listing():
    return {"id": "lbc_test_999", "transmission": "manual", "price": 2500, "year": 2010,
            "mileage_km": 80000, "city": "Paris", "lat": 48.8566, "lon": 2.3522,
            "seller_type": "private", "url": "https://lbc.fr/manual", "scraped_at": "2026-03-28T10:00:00Z"}
```

## test_scraper.py

```python
# TDD — write these tests BEFORE scraper code

def test_lbc_returns_raw_listings(lbc_html_fixture):
    """Scraper must return list[RawListing], not empty."""
    results = parse_lbc_html(lbc_html_fixture)
    assert len(results) > 0
    assert all(isinstance(r, RawListing) for r in results)

def test_lbc_filters_out_manual_in_title():
    """Listings with 'manuelle' in title must have transmission='manual'."""
    # scraper sets transmission, analyst excludes — separation of concerns
    pass

def test_price_parsing_handles_nbsp():
    """'3 200 €' (non-breaking space) must parse to 3200."""
    assert parse_price("3\u00a0200\u00a0€") == 3200

def test_deduplication(duplicate_listings):
    """Duplicate IDs across two scrape runs must collapse to one."""
    merged = deduplicate(run1 + run2)
    assert len(merged) == len(set(l.id for l in merged))

def test_fallback_chain_on_403(mock_403_response):
    """On LBC 403, must fall back to __NEXT_DATA__ then HTML."""
    # mock requests to return 403 on first call
    results = scrape_lbc_with_fallback()
    assert results is not None    # partial OK, not crash
```

## test_analyst.py

```python
def test_manual_transmission_excluded(manual_listing, analyst_agent):
    """Manual transmission = score -1, excluded=True. No exceptions."""
    result = analyst_agent.score(manual_listing)
    assert result.excluded is True
    assert result.score == -1
    assert "manual" in result.exclusion_reason.lower()

def test_over_budget_excluded(analyst_agent):
    listing = {..., "price": 5500}
    result = analyst_agent.score(listing)
    assert result.excluded is True

def test_score_schema_valid(sample_raw_listings, analyst_agent):
    """All scored listings must pass Pydantic ScoredListing validation."""
    results = analyst_agent.score_batch(sample_raw_listings)
    for r in results:
        ScoredListing(**r.dict())    # raises on schema violation

def test_score_range(single_auto_listing, analyst_agent):
    """Non-excluded listings: score must be 0-100."""
    result = analyst_agent.score(single_auto_listing)
    if not result.excluded:
        assert 0 <= result.score <= 100

def test_retry_on_bad_json(mock_bad_llm_response, analyst_agent):
    """Bad JSON from LLM triggers 2 retries, then analyst_failure flag."""
    result = analyst_agent.score_with_fallback(bad_listing)
    assert result.score == -2
    assert result.exclusion_reason == "analyst_failure"
```

## test_data.py

```python
def test_pydantic_rejects_invalid_score():
    with pytest.raises(ValueError):
        ScoredListing(..., score=150)

def test_haversine_orly_vitry():
    """Vitry-sur-Seine ~7km from Orly. Must return proximity score 15."""
    score = orly_distance_score(48.793, 2.392)
    assert score == 15

def test_state_roundtrip(tmp_path):
    """write_state then read_state must return identical dict."""
    state = {"last_scrape": "2026-03-28T10:00:00Z", "scrape_count": 3}
    write_state(state, path=tmp_path / "state.json")
    assert read_state(path=tmp_path / "state.json") == state
```

## test_supervisor.py

```python
def test_supervisor_scrapes_when_stale(mock_stale_state, mock_scraper):
    """If state shows no data, supervisor must call scrape_platforms."""
    supervisor.run(max_iterations=2)
    assert mock_scraper.called

def test_supervisor_skips_scrape_when_fresh(mock_fresh_state, mock_scraper):
    """If data < 24h old, no rescrape unless forced."""
    supervisor.run(max_iterations=2)
    assert not mock_scraper.called

def test_supervisor_handles_zero_listings(mock_empty_scrape, mock_ask_human):
    """Zero listings → asks human, does not crash."""
    supervisor.run(max_iterations=3)
    assert mock_ask_human.called
```

## Green/Red gates (mandatory before phase promotion)

| Phase | Gate | Pass criteria | Fail action |
|-------|------|--------------|-------------|
| Scraper | Unit | 100% tests GREEN, 0 import errors | Fix before proceeding |
| Data models | Unit | All Pydantic validators pass | Fix before analyst |
| Analyst | Unit | manual=excluded (HARD), schema valid | Block release |
| Integration | Full pipeline | 0 crashes, shortlist non-empty (if listings exist) | Debug loop |
| Security | Secrets scan | 0 keys in code or logs | Block release |

## Coverage targets

```bash
pytest --cov=. --cov-report=term-missing
# Targets:
# scraper_lbc.py: 80%+
# agent_analyst.py: 70%+
# models.py: 95%+
# utils.py: 90%+
```

## Key commands

```bash
pytest tests/ -v                          # all tests
pytest tests/test_scraper.py -v           # scraper only
pytest tests/ -k "manual"                 # transmission exclusion tests
pytest tests/ --cov=. --cov-report=html   # coverage report
```
