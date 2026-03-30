import os
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from scraper_lacentrale import (
    parse_lacentrale_nextdata, scrape_lacentrale, geocode_city,
    _is_block_page, _human_wiggle, _human_scroll,
    _parse_mileage, _parse_price,
)
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


def _make_mock_page(html_content, nextdata_len=100):
    """Create a mock Playwright page that returns given HTML."""
    page = MagicMock()
    page.content.return_value = html_content
    page.evaluate.return_value = nextdata_len
    page.goto.return_value = None
    page.mouse = MagicMock()
    page.close.return_value = None
    return page


PW_PATCH = "playwright.sync_api.sync_playwright"


@patch("scraper_lacentrale._polite_sleep")
@patch("scraper_lacentrale._human_scroll")
@patch("scraper_lacentrale._human_wiggle")
def test_scrape_lacentrale_cdp(mock_wiggle, mock_scroll, mock_sleep):
    """scrape_lacentrale connects via CDP and extracts listings."""
    fixture_html = load_fixture()

    mock_page = _make_mock_page(fixture_html)
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]

    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.connect_over_cdp.return_value = mock_browser

    mock_pw_cm = MagicMock()
    mock_pw_cm.__enter__ = MagicMock(return_value=mock_pw_instance)
    mock_pw_cm.__exit__ = MagicMock(return_value=False)

    with patch(PW_PATCH, return_value=mock_pw_cm):
        listings = scrape_lacentrale()

    assert len(listings) >= 1
    assert listings[0].platform == "lacentrale"
    mock_pw_instance.chromium.connect_over_cdp.assert_called_once()
    mock_page.close.assert_called_once()


@patch("scraper_lacentrale._polite_sleep")
def test_scrape_lacentrale_cdp_not_available(mock_sleep):
    """Chrome CDP not running → empty list, no crash."""
    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.connect_over_cdp.side_effect = ConnectionError(
        "connect ECONNREFUSED 127.0.0.1:9222"
    )
    mock_pw_cm = MagicMock()
    mock_pw_cm.__enter__ = MagicMock(return_value=mock_pw_instance)
    mock_pw_cm.__exit__ = MagicMock(return_value=False)

    with patch(PW_PATCH, return_value=mock_pw_cm):
        listings = scrape_lacentrale()
        assert listings == []


@patch("scraper_lacentrale._polite_sleep")
@patch("scraper_lacentrale._human_scroll")
@patch("scraper_lacentrale._human_wiggle")
def test_scrape_lacentrale_block_detected(mock_wiggle, mock_scroll, mock_sleep):
    """DataDome block page → empty list."""
    block_html = '<html><body><p>captcha</p><script>datadome</script></body></html>'
    mock_page = _make_mock_page(block_html, nextdata_len=0)
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]

    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.connect_over_cdp.return_value = mock_browser
    mock_pw_cm = MagicMock()
    mock_pw_cm.__enter__ = MagicMock(return_value=mock_pw_instance)
    mock_pw_cm.__exit__ = MagicMock(return_value=False)

    with patch(PW_PATCH, return_value=mock_pw_cm):
        listings = scrape_lacentrale()

    assert listings == []
    mock_page.close.assert_called_once()


def test_is_block_page():
    assert _is_block_page('<html>captcha challenge</html>') is True
    assert _is_block_page('<html>datadome protected</html>') is True
    assert _is_block_page('<html>Please enable JS</html>') is True
    assert _is_block_page('<html><body>normal page</body></html>') is False
    assert _is_block_page('') is False
    assert _is_block_page(None) is False


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




def test_parse_nextdata_no_cards():
    """Valid __NEXT_DATA__ with HTML content but no vehicle cards → empty list."""
    import json
    nextdata = {
        "props": {
            "pageProps": {
                "data": {
                    "content": "<div>No results found</div>"
                }
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(nextdata)}</script></body></html>'
    listings = parse_lacentrale_nextdata(html)
    assert listings == []


def test_parse_nextdata_empty_content():
    """Valid __NEXT_DATA__ with empty content → empty list."""
    import json
    nextdata = {"props": {"pageProps": {"data": {"content": ""}}}}
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(nextdata)}</script></body></html>'
    listings = parse_lacentrale_nextdata(html)
    assert listings == []


def test_parse_mileage():
    assert _parse_mileage("63 000 km") == 63000
    assert _parse_mileage("97 900 km") == 97900
    assert _parse_mileage("150000 km") == 150000
    assert _parse_mileage("no mileage") is None
    assert _parse_mileage("") is None


def test_parse_price():
    assert _parse_price("6 280 €") == 6280
    assert _parse_price("2 900 €") == 2900
    assert _parse_price("11 990 €") == 11990
    assert _parse_price("") == 0


def test_parse_nextdata_dedup():
    """Duplicate cards (same href) are deduplicated."""
    import json
    card = '''<a href="/auto-occasion-annonce-12345.html" data-testid="vehicleCardV2">
        <span class="vehiclecardV2_title__x">TOYOTA IQ</span>
        <span class="vehiclecardV2_vehiclePrice__x">3000 €</span>
    </a>'''
    nextdata = {"props": {"pageProps": {"data": {"content": card + card}}}}
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(nextdata)}</script></body></html>'
    listings = parse_lacentrale_nextdata(html)
    assert len(listings) == 1


def test_parse_nextdata_private_seller():
    """Card without seller element → seller_type = private."""
    import json
    card = '''<a href="/auto-occasion-annonce-99999.html" data-testid="vehicleCardV2">
        <span class="vehiclecardV2_title__x">TOYOTA IQ</span>
        <span class="vehiclecardV2_vehiclePrice__x">2500 €</span>
        <span class="vehiclecardV2_locationText__x">75</span>
    </a>'''
    nextdata = {"props": {"pageProps": {"data": {"content": card}}}}
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(nextdata)}</script></body></html>'
    listings = parse_lacentrale_nextdata(html)
    assert len(listings) == 1
    assert listings[0].seller_type == "private"
    assert listings[0].department == "75"


def test_human_wiggle():
    """human_wiggle calls mouse.move without crashing."""
    page = MagicMock()
    page.mouse = MagicMock()
    with patch("scraper_lacentrale.time.sleep"):
        _human_wiggle(page)
    page.mouse.move.assert_called_once()


def test_human_scroll():
    """human_scroll calls mouse.wheel the specified number of times."""
    page = MagicMock()
    page.mouse = MagicMock()
    with patch("scraper_lacentrale.time.sleep"):
        _human_scroll(page, times=3)
    assert page.mouse.wheel.call_count == 3
