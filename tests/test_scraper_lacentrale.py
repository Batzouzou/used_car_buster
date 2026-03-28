import os
import pytest
from unittest.mock import patch, MagicMock
from scraper_lacentrale import parse_lacentrale_nextdata, scrape_lacentrale, geocode_city
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


def test_geocode_city_cache_hit():
    coords = geocode_city("paris")
    assert coords is not None
    assert abs(coords[0] - 48.8566) < 0.01
    assert abs(coords[1] - 2.3522) < 0.01


def test_geocode_city_cache_hit_case_insensitive():
    coords = geocode_city("PARIS")
    assert coords is not None
    assert abs(coords[0] - 48.8566) < 0.01


def test_geocode_city_none_for_empty():
    assert geocode_city("") is None
    assert geocode_city(None) is None


def test_parse_nextdata_malformed_json():
    """Malformed JSON in __NEXT_DATA__ → empty list (not crash)."""
    html = '<html><body><script id="__NEXT_DATA__" type="application/json">{bad json!!!</script></body></html>'
    listings = parse_lacentrale_nextdata(html)
    assert listings == []


def test_geocode_city_known_cities():
    """Several known cities return valid coords."""
    for city in ["lyon", "marseille", "toulouse"]:
        coords = geocode_city(city)
        assert coords is not None, f"No coords for {city}"
        assert 42.0 < coords[0] < 49.0, f"Bad lat for {city}"
        assert -2.0 < coords[1] < 8.0, f"Bad lon for {city}"


def test_geocode_city_disk_cache_hit(tmp_path):
    """City in disk cache but not memory cache → returns from disk, no Nominatim."""
    import json
    cache_file = tmp_path / "geocode_cache.json"
    cache_file.write_text(json.dumps({"testville": [45.0, 3.0]}), encoding="utf-8")

    with patch("scraper_lacentrale.OUTPUT_DIR", str(tmp_path)), \
         patch("scraper_lacentrale.CITY_COORDS_CACHE", {}), \
         patch("scraper_lacentrale.requests.get") as mock_get:
        coords = geocode_city("Testville")
        assert coords == (45.0, 3.0)
        mock_get.assert_not_called()  # no Nominatim call


def test_geocode_city_disk_cache_malformed(tmp_path):
    """Corrupted disk cache → ignored, falls through to Nominatim."""
    cache_file = tmp_path / "geocode_cache.json"
    cache_file.write_text("{broken json!!!", encoding="utf-8")

    with patch("scraper_lacentrale.OUTPUT_DIR", str(tmp_path)), \
         patch("scraper_lacentrale.CITY_COORDS_CACHE", {}), \
         patch("scraper_lacentrale.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"lat": "46.0", "lon": "4.0"}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        coords = geocode_city("SomeCity")
        assert coords == (46.0, 4.0)
        mock_get.assert_called_once()


def test_geocode_city_nominatim_empty_results(tmp_path):
    """Nominatim returns empty list → None."""
    with patch("scraper_lacentrale.OUTPUT_DIR", str(tmp_path)), \
         patch("scraper_lacentrale.CITY_COORDS_CACHE", {}), \
         patch("scraper_lacentrale.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        coords = geocode_city("NonexistentVille")
        assert coords is None


def test_geocode_city_nominatim_exception(tmp_path):
    """Nominatim network error → None (not crash)."""
    with patch("scraper_lacentrale.OUTPUT_DIR", str(tmp_path)), \
         patch("scraper_lacentrale.CITY_COORDS_CACHE", {}), \
         patch("scraper_lacentrale.requests.get", side_effect=ConnectionError("timeout")):
        coords = geocode_city("AnyCity")
        assert coords is None


def test_geocode_city_nominatim_writes_disk_cache(tmp_path):
    """Successful Nominatim lookup writes to disk cache."""
    import json
    with patch("scraper_lacentrale.OUTPUT_DIR", str(tmp_path)), \
         patch("scraper_lacentrale.CITY_COORDS_CACHE", {}), \
         patch("scraper_lacentrale.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"lat": "47.5", "lon": "3.5"}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        coords = geocode_city("NewCity")
        assert coords == (47.5, 3.5)
        # Verify disk cache was written
        cache_file = tmp_path / "geocode_cache.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert "newcity" in data


@patch("scraper_lacentrale.requests.Session")
def test_scrape_lacentrale_exception(mock_session_cls):
    """scrape_lacentrale with network exception → empty list."""
    mock_session = MagicMock()
    mock_session.get.side_effect = ConnectionError("DNS failed")
    mock_session_cls.return_value = mock_session
    listings = scrape_lacentrale()
    assert listings == []


def test_parse_nextdata_listing_parse_exception():
    """Listing with malformed data inside valid __NEXT_DATA__ → skipped."""
    import json
    nextdata = {
        "props": {
            "pageProps": {
                "searchData": {
                    "results": [
                        {"id": None, "price": "not_a_number"}  # will cause exception
                    ]
                }
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(nextdata)}</script></body></html>'
    listings = parse_lacentrale_nextdata(html)
    assert listings == []  # malformed item skipped
