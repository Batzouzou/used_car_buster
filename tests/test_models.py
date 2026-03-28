import pytest
from datetime import datetime, timezone
from models import RawListing, ScoredListing, PricedListing, ScoreBreakdown

def test_raw_listing_valid():
    listing = RawListing(
        id="lbc_123", platform="leboncoin", title="Toyota iQ 1.33 CVT",
        price=3200, year=2011, mileage_km=78000, transmission="auto",
        fuel="essence", city="Paris", department="75", lat=48.85, lon=2.35,
        seller_type="pro", url="https://www.leboncoin.fr/voitures/123",
        description="Bon etat", images=["img1.jpg"],
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
    assert listing.id == "lbc_123"
    assert listing.platform == "leboncoin"

def test_raw_listing_optional_fields():
    listing = RawListing(
        id="lc_456", platform="lacentrale", title="iQ auto",
        price=2800, year=2010, seller_type="private",
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

def test_score_breakdown_valid():
    bd = ScoreBreakdown(price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10)
    assert bd.price == 25

def test_score_breakdown_condition_capped_at_10():
    bd = ScoreBreakdown(price=0, mileage=0, year=0, proximity=0, condition=15, transmission=0)
    assert bd.condition == 10

def test_scored_listing_valid():
    raw = RawListing(
        id="lbc_1", platform="leboncoin", title="iQ", price=3000,
        year=2012, seller_type="pro", url="http://x",
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
    scored = ScoredListing(
        **raw.model_dump(),
        score=78,
        score_breakdown=ScoreBreakdown(price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10),
        excluded=False, red_flags=[], highlights=["CT OK"], concerns=[], summary_fr="Bonne affaire",
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
        score_breakdown=ScoreBreakdown(price=0, mileage=0, year=0, proximity=0, condition=0, transmission=0),
        excluded=True, exclusion_reason="Manual transmission",
        red_flags=["manual"], highlights=[], concerns=[], summary_fr="Exclue: manuelle",
    )
    assert scored.excluded is True
    assert scored.exclusion_reason == "Manual transmission"

def test_priced_listing_valid():
    raw = RawListing(
        id="lbc_1", platform="leboncoin", title="iQ", price=3000,
        year=2012, seller_type="pro", url="http://x",
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
    scored = ScoredListing(
        **raw.model_dump(),
        score=78,
        score_breakdown=ScoreBreakdown(price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10),
        excluded=False, red_flags=[], highlights=[], concerns=[], summary_fr="OK",
    )
    priced = PricedListing(
        **scored.model_dump(),
        market_estimate_low=2500, market_estimate_high=3200,
        opening_offer=2400, max_acceptable=3000,
        anchors=["km eleve"], message_digital="Bonjour...",
        message_oral_points=["Mentionner km"],
    )
    assert priced.opening_offer == 2400
    assert priced.market_estimate_low < priced.market_estimate_high
