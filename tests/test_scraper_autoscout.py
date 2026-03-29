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


# --- New format tests (2026 __NEXT_DATA__ structure) ---

NEW_FORMAT_LISTING = {
    "id": "cd90ece6-5ed5-409a-8878-a5b599bf5511",
    "price": {
        "priceFormatted": "\u20ac 5\u202f990",
        "priceEvaluation": 2,
    },
    "url": "/offres/toyota-iq-1-0-vvti-cd90ece6",
    "vehicle": {
        "make": "Toyota",
        "model": "iQ",
        "subtitle": "Toyota Iq 1.0 vvti 46004 kms",
        "transmission": "Bo\u00eete manuelle",
        "fuel": "Essence",
        "mileageInKm": "46\u202f000 km",
    },
    "location": {
        "countryCode": "FR",
        "zip": "41000",
        "city": "Blois",
    },
    "seller": {
        "type": "Dealer",
        "companyName": "Power Auto",
    },
    "tracking": {
        "firstRegistration": "10-2009",
        "mileage": "46000",
        "price": "5990",
        "fuelType": "b",
    },
    "images": ["https://img.autoscout24.net/photo1.jpg"],
}

NEW_FORMAT_LISTING_PRIVATE_AUTO = {
    "id": "aaa-bbb-ccc",
    "price": {
        "priceFormatted": "\u20ac 3\u202f200",
    },
    "url": "/offres/toyota-iq-aaa-bbb-ccc",
    "vehicle": {
        "make": "Toyota",
        "model": "iQ",
        "subtitle": "Toyota iQ 1.33 Multidrive",
        "transmission": "Bo\u00eete automatique",
        "fuel": "Essence",
        "mileageInKm": "78\u202f000 km",
    },
    "location": {
        "countryCode": "FR",
        "city": "Paris",
    },
    "seller": {
        "type": "Private",
    },
    "tracking": {
        "firstRegistration": "03-2012",
        "mileage": "78000",
        "price": "3200",
    },
    "images": [],
}


def test_parse_new_format_price():
    """New format: price is a dict with priceFormatted, must extract int."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING])
    assert len(listings) == 1
    assert listings[0].price == 5990


def test_parse_new_format_mileage():
    """New format: mileage in vehicle.mileageInKm as string with spaces."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING])
    assert listings[0].mileage_km == 46000


def test_parse_new_format_year():
    """New format: firstRegistration in tracking as '10-2009'."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING])
    assert listings[0].year == 2009


def test_parse_new_format_transmission_manual():
    """New format: vehicle.transmission 'Boite manuelle' → 'manual'."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING])
    assert listings[0].transmission == "manual"


def test_parse_new_format_transmission_auto():
    """New format: vehicle.transmission 'Boite automatique' → 'auto'."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING_PRIVATE_AUTO])
    assert listings[0].transmission == "auto"


def test_parse_new_format_seller_dealer():
    """New format: seller.type='Dealer' → 'pro'."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING])
    assert listings[0].seller_type == "pro"


def test_parse_new_format_seller_private():
    """New format: seller.type='Private' → 'private'."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING_PRIVATE_AUTO])
    assert listings[0].seller_type == "private"


def test_parse_new_format_title():
    """New format: title from vehicle.subtitle."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING])
    assert "Toyota" in listings[0].title
    assert "iQ" in listings[0].title or "Iq" in listings[0].title


def test_parse_new_format_url():
    """New format: relative URL must get full domain prepended."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING])
    assert listings[0].url.startswith("https://www.autoscout24.fr/")


def test_parse_new_format_city():
    """New format: location.city present."""
    listings = parse_autoscout_listings([NEW_FORMAT_LISTING])
    assert listings[0].city == "Blois"
