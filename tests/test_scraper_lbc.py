import json
import os
import pytest
from unittest.mock import patch, MagicMock
from scraper_lbc import (
    parse_lbc_listings, scrape_leboncoin, _scrape_lbc_fallback,
    _build_search_url, _parse_nextdata_ads,
)
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
    assert listings[0].transmission == "auto"
    assert listings[1].transmission == "manual"

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
    mock_session.post.return_value = mock_resp
    mock_session_cls.return_value = mock_session

    listings = scrape_leboncoin()
    assert len(listings) >= 1
    assert all(isinstance(l, RawListing) for l in listings)


def test_build_search_url():
    """Search URL contains brand, model, gearbox=2, and Orly coords."""
    url = _build_search_url()
    assert "leboncoin.fr/recherche" in url
    assert "category=2" in url
    assert "u_car_brand=TOYOTA" in url
    assert "_u_car_model=TOYOTA_iQ" in url
    assert "gearbox=2" in url
    assert "48.7262" in url


def test_parse_nextdata_ads_valid():
    """__NEXT_DATA__ with ads → returns ad list."""
    html = '<html><script id="__NEXT_DATA__" type="application/json">'
    html += json.dumps({"props": {"pageProps": {"searchData": {"ads": [
        {"list_id": 1, "subject": "iQ", "price": [3000],
         "attributes": [], "location": {}, "owner": {},
         "url": "http://x", "body": "", "images": {}}
    ]}}}})
    html += '</script></html>'
    ads = _parse_nextdata_ads(html)
    assert len(ads) == 1
    assert ads[0]["list_id"] == 1


def test_parse_nextdata_ads_missing():
    """No __NEXT_DATA__ script tag → empty list."""
    assert _parse_nextdata_ads("<html><body>No data</body></html>") == []


def test_parse_nextdata_ads_malformed_json():
    """__NEXT_DATA__ with invalid JSON → empty list."""
    html = '<html><script id="__NEXT_DATA__">not json</script></html>'
    assert _parse_nextdata_ads(html) == []


@patch("scraper_lbc.time.sleep")
def test_scrape_lbc_fallback_with_ads(mock_sleep):
    """Fallback scrapes HTML and returns listings."""
    ads_data = {"props": {"pageProps": {"searchData": {"ads": [
        {"list_id": 77, "subject": "iQ Auto", "price": [2900],
         "attributes": [], "location": {}, "owner": {},
         "url": "http://x", "body": "", "images": {}}
    ]}}}}
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(ads_data)}</script></html>'
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    session.get.return_value = mock_resp
    result = _scrape_lbc_fallback(session)
    assert len(result) == 1
    assert result[0].id == "lbc_77"


@patch("scraper_lbc.time.sleep")
def test_scrape_lbc_fallback_no_ads(mock_sleep):
    """Fallback with empty __NEXT_DATA__ → empty list."""
    html = '<html><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{}}}</script></html>'
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    session.get.return_value = mock_resp
    result = _scrape_lbc_fallback(session)
    assert result == []


def test_scrape_lbc_fallback_exception():
    """Fallback with network error → empty list, no crash."""
    session = MagicMock()
    session.get.side_effect = ConnectionError("timeout")
    result = _scrape_lbc_fallback(session)
    assert result == []


def test_parse_lbc_exception_in_ad_skips():
    """Ad missing 'list_id' key → skipped, rest parsed."""
    ads = [
        {},  # missing list_id → exception → skip
        {"list_id": 42, "subject": "Good Ad", "price": [2000],
         "attributes": [], "location": {}, "owner": {},
         "url": "http://x", "body": "", "images": {}},
    ]
    listings = parse_lbc_listings(ads)
    assert len(listings) == 1
    assert listings[0].id == "lbc_42"


def test_parse_lbc_empty_price_list():
    """price=[] → defaults to 0."""
    ads = [{"list_id": 1, "subject": "Test", "price": [],
            "attributes": [], "location": {}, "owner": {},
            "url": "http://x", "body": "", "images": {}}]
    listings = parse_lbc_listings(ads)
    assert len(listings) == 1
    assert listings[0].price == 0


@patch("scraper_lbc.requests.Session")
def test_scrape_leboncoin_pagination(mock_session_cls):
    """Two-page scrape: first page has 2 ads + total=3, second page has 1 ad."""
    page1_data = {
        "ads": [
            {"list_id": 1, "subject": "iQ 1", "price": [3000],
             "attributes": [], "location": {}, "owner": {},
             "url": "http://x", "body": "", "images": {}},
            {"list_id": 2, "subject": "iQ 2", "price": [3200],
             "attributes": [], "location": {}, "owner": {},
             "url": "http://x", "body": "", "images": {}},
        ],
        "total": 3,
    }
    page2_data = {
        "ads": [
            {"list_id": 3, "subject": "iQ 3", "price": [2800],
             "attributes": [], "location": {}, "owner": {},
             "url": "http://x", "body": "", "images": {}},
        ],
        "total": 3,
    }

    mock_session = MagicMock()
    mock_resp1 = MagicMock()
    mock_resp1.json.return_value = page1_data
    mock_resp1.raise_for_status = MagicMock()
    mock_resp2 = MagicMock()
    mock_resp2.json.return_value = page2_data
    mock_resp2.raise_for_status = MagicMock()
    mock_session.post.side_effect = [mock_resp1, mock_resp2]
    mock_session_cls.return_value = mock_session

    listings = scrape_leboncoin()
    assert len(listings) == 3


@patch("scraper_lbc.requests.Session")
def test_scrape_leboncoin_http_403_uses_fallback(mock_session_cls):
    """HTTP 403 → calls _scrape_lbc_fallback."""
    import requests as real_requests
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.raise_for_status.side_effect = real_requests.exceptions.HTTPError(
        response=mock_resp
    )
    mock_session.post.return_value = mock_resp
    mock_session_cls.return_value = mock_session

    listings = scrape_leboncoin()
    assert listings == []  # fallback returns []


@patch("scraper_lbc.requests.Session")
def test_scrape_leboncoin_pagination_empty_page_breaks(mock_session_cls):
    """Pagination: second page returns empty ads → loop breaks."""
    page1_data = {
        "ads": [
            {"list_id": 1, "subject": "iQ", "price": [3000],
             "attributes": [], "location": {}, "owner": {},
             "url": "http://x", "body": "", "images": {}},
        ],
        "total": 100,  # claims 100, but page 2 is empty
    }
    page2_data = {"ads": [], "total": 100}

    mock_session = MagicMock()
    mock_resp1 = MagicMock()
    mock_resp1.json.return_value = page1_data
    mock_resp1.raise_for_status = MagicMock()
    mock_resp2 = MagicMock()
    mock_resp2.json.return_value = page2_data
    mock_resp2.raise_for_status = MagicMock()
    mock_session.post.side_effect = [mock_resp1, mock_resp2]
    mock_session_cls.return_value = mock_session

    listings = scrape_leboncoin()
    assert len(listings) == 1  # only page 1's listing, loop broke on empty page 2


@patch("scraper_lbc.requests.Session")
def test_scrape_leboncoin_http_500_logs_error(mock_session_cls):
    """HTTP 500 → not 403/429 → error logged, empty list returned."""
    import requests as real_requests
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = real_requests.exceptions.HTTPError(
        response=mock_resp
    )
    mock_session.post.return_value = mock_resp
    mock_session_cls.return_value = mock_session

    listings = scrape_leboncoin()
    assert listings == []


@patch("scraper_lbc.requests.Session")
def test_scrape_leboncoin_http_error_no_response(mock_session_cls):
    """HTTPError with e.response=None → else branch, no crash."""
    import requests as real_requests
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = real_requests.exceptions.HTTPError(
        response=None
    )
    mock_session.post.return_value = mock_resp
    mock_session_cls.return_value = mock_session

    listings = scrape_leboncoin()
    assert listings == []


@patch("scraper_lbc.requests.Session")
def test_scrape_leboncoin_generic_exception(mock_session_cls):
    """Non-HTTP exception (e.g., ConnectionError) → logged, empty list."""
    mock_session = MagicMock()
    mock_session.post.side_effect = ConnectionError("DNS resolution failed")
    mock_session_cls.return_value = mock_session

    listings = scrape_leboncoin()
    assert listings == []
