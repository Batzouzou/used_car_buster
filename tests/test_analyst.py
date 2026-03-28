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


def test_analyze_empty_listings():
    """Empty input → ([], []) without calling LLM."""
    mock_client = MagicMock()
    pro, part = analyze_listings([], mock_client)
    assert pro == []
    assert part == []
    mock_client.query.assert_not_called()


def test_analyze_invalid_json_from_llm():
    """LLM returns non-JSON → ([], [])."""
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text="Sorry, I cannot parse these listings.",
        model_used="ollama",
        raw=None,
    )
    listings = [_make_listing()]
    pro, part = analyze_listings(listings, mock_client)
    assert pro == []
    assert part == []


def test_analyze_llm_returns_object_not_array():
    """LLM returns JSON object instead of array → ([], [])."""
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text='{"error": "something went wrong"}',
        model_used="ollama",
        raw=None,
    )
    listings = [_make_listing()]
    pro, part = analyze_listings(listings, mock_client)
    assert pro == []
    assert part == []


def test_analyze_unknown_id_in_llm_response():
    """LLM returns an ID not in listings → skipped silently."""
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text='[{"id":"lbc_999","score":80,"score_breakdown":{"price":25,"mileage":15,"year":10,"proximity":8,"condition":10,"transmission":10},"excluded":false,"red_flags":[],"highlights":[],"concerns":[],"summary_fr":"OK"}]',
        model_used="ollama",
        raw=None,
    )
    listings = [_make_listing(id="lbc_1")]
    pro, part = analyze_listings(listings, mock_client)
    assert pro == []
    assert part == []


def test_analyze_malformed_item_in_response():
    """LLM returns item missing score_breakdown → skipped with warning."""
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text='[{"id":"lbc_1","score":78}]',
        model_used="ollama",
        raw=None,
    )
    listings = [_make_listing()]
    pro, part = analyze_listings(listings, mock_client)
    assert pro == []
    assert part == []


def _make_scored_json(id, score, seller_type="pro"):
    return {
        "id": id, "score": score, "excluded": False,
        "score_breakdown": {"price": 20, "mileage": 15, "year": 10, "proximity": 8, "condition": 10, "transmission": 10},
        "red_flags": [], "highlights": [], "concerns": [], "summary_fr": "OK",
    }


def test_analyze_top_n_limits_results():
    """top_n=1 limits each shortlist to 1 item."""
    import json

    listings = [
        _make_listing(id="lbc_1"),
        _make_listing(id="lbc_2"),
        _make_listing(id="lbc_3"),
    ]
    scored = [
        _make_scored_json("lbc_1", 90),
        _make_scored_json("lbc_2", 80),
        _make_scored_json("lbc_3", 70),
    ]
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text=json.dumps(scored), model_used="ollama", raw=None,
    )
    pro, part = analyze_listings(listings, mock_client, top_n=1)
    assert len(pro) == 1
    assert pro[0].id == "lbc_1"  # highest score
