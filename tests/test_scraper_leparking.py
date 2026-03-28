"""Tests for Le Parking scraper."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from scraper_leparking import parse_leparking_html, scrape_leparking, _parse_price, _parse_mileage, _parse_year

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "leparking_sample.html"


def test_parse_leparking_html():
    """Test parsing Le Parking HTML fixture into RawListing models."""
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    listings = parse_leparking_html(html)
    assert len(listings) == 2

    first = listings[0]
    assert first.platform == "leparking"
    assert first.id.startswith("lp_")
    assert first.price > 0
    assert first.year >= 2009
    assert first.city is not None


def test_parse_leparking_seller_types():
    """Test that seller types are correctly parsed."""
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    listings = parse_leparking_html(html)
    seller_types = {l.seller_type for l in listings}
    assert "pro" in seller_types or "private" in seller_types


def test_scrape_leparking_mocked():
    """Test scrape_leparking with mocked HTTP requests."""
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    with patch("scraper_leparking.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session
        with patch("scraper_leparking.time.sleep"):
            listings = scrape_leparking()
            assert len(listings) == 2


def test_parse_price_euros():
    assert _parse_price("3 200 EUR") == 3200


def test_parse_price_euro_symbol():
    assert _parse_price("3200€") == 3200


def test_parse_price_no_digits():
    assert _parse_price("Prix sur demande") == 0


def test_parse_mileage_with_spaces():
    assert _parse_mileage("78 000 km") == 78000


def test_parse_mileage_no_digits():
    assert _parse_mileage("km non renseigne") is None


def test_parse_year_found():
    assert _parse_year("2011") == 2011


def test_parse_year_in_parens():
    assert _parse_year("(2013)") == 2013


def test_parse_year_not_found():
    assert _parse_year("unknown") == 2009


def test_parse_leparking_empty_html():
    """No .vehicle-card elements → empty list."""
    html = "<html><body><div>No cars here</div></body></html>"
    listings = parse_leparking_html(html)
    assert listings == []


def test_parse_leparking_card_exception_skipped():
    """Exception during card parsing → skipped, not crash."""
    html = '<html><body><div class="vehicle-card"><span class="location">Paris (75)</span></div></body></html>'
    with patch("scraper_leparking.geocode_city", side_effect=Exception("boom")):
        listings = parse_leparking_html(html)
        assert listings == []  # exception caught, card skipped


@patch("scraper_leparking.requests.Session")
def test_scrape_leparking_generic_exception(mock_session_cls):
    """Generic exception during scrape → logged, returns empty list."""
    mock_session = MagicMock()
    mock_session.get.side_effect = ConnectionError("network down")
    mock_session_cls.return_value = mock_session

    from scraper_leparking import scrape_leparking
    listings = scrape_leparking()
    assert listings == []
