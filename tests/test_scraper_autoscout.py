import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from scraper_autoscout import parse_autoscout_listings, scrape_autoscout24, _extract_year

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "autoscout_sample.json"


def test_parse_autoscout_listings():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    listings_data = data["props"]["pageProps"]["listings"]
    listings = parse_autoscout_listings(listings_data)
    assert len(listings) == 2

    first = listings[0]
    assert first.platform == "autoscout24"
    assert first.id.startswith("as_")
    assert first.price > 0
    assert first.year >= 2009
    assert first.lat is not None
    assert first.lon is not None


def test_parse_autoscout_seller_types():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    listings_data = data["props"]["pageProps"]["listings"]
    listings = parse_autoscout_listings(listings_data)
    types = {l.seller_type for l in listings}
    assert "pro" in types
    assert "private" in types


def test_scrape_autoscout_mocked():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    # Build HTML page with __NEXT_DATA__ script tag
    html = f'''<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'''

    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    with patch("scraper_autoscout.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session
        with patch("scraper_autoscout.time.sleep"):
            listings = scrape_autoscout24()
            assert len(listings) == 2


def test_extract_year_slash_format():
    assert _extract_year("01/2011") == 2011


def test_extract_year_plain():
    assert _extract_year("2013") == 2013


def test_extract_year_empty():
    assert _extract_year("") == 2009


def test_extract_year_none():
    assert _extract_year(None) == 2009


def test_scrape_autoscout_no_next_data():
    """Page without __NEXT_DATA__ → empty list."""
    html = "<html><body><p>No data</p></body></html>"
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    with patch("scraper_autoscout.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session
        with patch("scraper_autoscout.time.sleep"):
            listings = scrape_autoscout24()
            assert listings == []


def test_parse_autoscout_gearbox_mapping():
    """gearType mapping: auto → 'auto', empty → None."""
    listings = parse_autoscout_listings([
        {"id": "1", "title": "iQ", "price": 3000, "firstRegistration": "2011",
         "mileage": 80000, "gearType": "Automatique", "sellerType": "D",
         "url": "/listing/1", "location": {}},
        {"id": "2", "title": "iQ", "price": 2500, "firstRegistration": "2010",
         "mileage": 90000, "gearType": "", "sellerType": "P",
         "url": "/listing/2", "location": {}},
    ])
    assert listings[0].transmission == "auto"
    assert listings[1].transmission is None


def test_parse_autoscout_listing_exception_skipped():
    """Malformed listing item → skipped, not crash."""
    listings = parse_autoscout_listings([
        {"id": None, "price": "bad"},  # will cause exception
    ])
    assert listings == []


@patch("scraper_autoscout.requests.Session")
def test_scrape_autoscout24_generic_exception(mock_session_cls):
    """Generic exception during scrape → logged, returns empty list."""
    mock_session = MagicMock()
    mock_session.get.side_effect = ConnectionError("network down")
    mock_session_cls.return_value = mock_session
    listings = scrape_autoscout24()
    assert listings == []
