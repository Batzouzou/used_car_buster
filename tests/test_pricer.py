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


def test_price_empty_listings():
    """Empty input → [] without calling LLM."""
    mock_client = MagicMock()
    result = price_listings([], mock_client)
    assert result == []
    mock_client.query.assert_not_called()


def test_price_invalid_json_from_llm():
    """LLM returns non-JSON → []."""
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text="I can't generate pricing data right now.",
        model_used="claude-sonnet-4-20250514",
        raw=None,
    )
    result = price_listings([_make_scored()], mock_client)
    assert result == []


def test_price_unknown_id_in_response():
    """LLM returns ID not in scored listings → skipped."""
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text='[{"id":"lbc_999","market_estimate_low":2500,"market_estimate_high":3200,"opening_offer":2400,"max_acceptable":3000}]',
        model_used="claude-sonnet-4-20250514",
        raw=None,
    )
    result = price_listings([_make_scored(id="lbc_1")], mock_client)
    assert result == []


def test_price_malformed_item_missing_fields():
    """LLM returns item missing required pricing fields → skipped."""
    mock_client = MagicMock()
    mock_client.query.return_value = LLMResponse(
        text='[{"id":"lbc_1","market_estimate_low":2500}]',
        model_used="claude-sonnet-4-20250514",
        raw=None,
    )
    result = price_listings([_make_scored()], mock_client)
    assert result == []
