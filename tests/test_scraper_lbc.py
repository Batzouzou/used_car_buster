# tests/test_scraper_lbc.py
"""Tests for LeBonCoin scraper (lbc library integration)."""
import pytest
from dataclasses import dataclass
from unittest.mock import patch, MagicMock
from scraper_lbc import _ad_to_listing, scrape_leboncoin
from models import RawListing


def _make_location(**overrides):
    """Create a mock lbc.Location dataclass."""
    defaults = dict(
        country_id="FR", region_id="12", region_name="Ile-de-France",
        department_id="94", department_name="Val-de-Marne",
        city_label="Vitry-sur-Seine", city="Vitry-sur-Seine",
        zipcode="94400", lat=48.787, lng=2.392,
        source="city", provider="here", is_shape=False,
    )
    defaults.update(overrides)
    loc = MagicMock()
    for k, v in defaults.items():
        setattr(loc, k, v)
    return loc


def _make_attribute(key, value, value_label=""):
    attr = MagicMock()
    attr.key = key
    attr.value = value
    attr.value_label = value_label
    return attr


def _make_ad(**overrides):
    """Create a mock lbc.Ad with sensible defaults."""
    defaults = dict(
        id=12345,
        subject="Toyota iQ 1.33 CVT Automatique",
        price=3200,
        body="Toyota iQ automatique, bon etat, CT OK",
        ad_type="pro",
        url="https://www.leboncoin.fr/voitures/12345.htm",
        images=["https://img.lbc.fr/1.jpg"],
        location=_make_location(),
        attributes=[
            _make_attribute("mileage", "78000"),
            _make_attribute("regdate", "2011"),
            _make_attribute("fuel", "1"),
            _make_attribute("gearbox", "2"),
        ],
    )
    defaults.update(overrides)
    ad = MagicMock()
    for k, v in defaults.items():
        setattr(ad, k, v)
    return ad


def _make_search_result(ads=None, max_pages=1):
    """Create a mock lbc.Search result."""
    result = MagicMock()
    result.ads = ads or []
    result.max_pages = max_pages
    return result


# --- _ad_to_listing ---

def test_ad_to_listing_basic():
    ad = _make_ad()
    listing = _ad_to_listing(ad)
    assert isinstance(listing, RawListing)
    assert listing.id == "lbc_12345"
    assert listing.platform == "leboncoin"
    assert listing.price == 3200
    assert listing.year == 2011
    assert listing.mileage_km == 78000
    assert listing.transmission == "auto"
    assert listing.seller_type == "pro"
    assert listing.city == "Vitry-sur-Seine"
    assert listing.lat == 48.787
    assert listing.lon == 2.392


def test_ad_to_listing_private_seller():
    ad = _make_ad(ad_type="private")
    listing = _ad_to_listing(ad)
    assert listing.seller_type == "private"


def test_ad_to_listing_manual_gearbox():
    ad = _make_ad(attributes=[
        _make_attribute("gearbox", "1"),
        _make_attribute("regdate", "2010"),
    ])
    listing = _ad_to_listing(ad)
    assert listing.transmission == "manual"


def test_ad_to_listing_missing_mileage():
    ad = _make_ad(attributes=[
        _make_attribute("gearbox", "2"),
        _make_attribute("regdate", "2011"),
    ])
    listing = _ad_to_listing(ad)
    assert listing.mileage_km is None


def test_ad_to_listing_missing_regdate():
    ad = _make_ad(attributes=[
        _make_attribute("gearbox", "2"),
    ])
    listing = _ad_to_listing(ad)
    assert listing.year == 2009  # default


def test_ad_to_listing_no_location():
    ad = _make_ad(location=None)
    listing = _ad_to_listing(ad)
    assert listing.city is None
    assert listing.lat is None
    assert listing.lon is None


def test_ad_to_listing_zero_price():
    ad = _make_ad(price=0)
    listing = _ad_to_listing(ad)
    assert listing.price == 0


def test_ad_to_listing_none_price():
    ad = _make_ad(price=None)
    listing = _ad_to_listing(ad)
    assert listing.price == 0


# --- scrape_leboncoin ---

@patch("scraper_lbc.lbc.Client")
def test_scrape_leboncoin_returns_listings(mock_client_cls):
    mock_client = MagicMock()
    mock_client.search.return_value = _make_search_result(
        ads=[_make_ad(id=1), _make_ad(id=2)], max_pages=1,
    )
    mock_client_cls.return_value = mock_client

    listings = scrape_leboncoin()
    assert len(listings) == 2
    assert all(isinstance(l, RawListing) for l in listings)
    mock_client.search.assert_called_once()


@patch("scraper_lbc.lbc.Client")
def test_scrape_leboncoin_pagination(mock_client_cls):
    """Two pages: page 1 has 2 ads, page 2 has 1 ad."""
    mock_client = MagicMock()
    mock_client.search.side_effect = [
        _make_search_result(ads=[_make_ad(id=1), _make_ad(id=2)], max_pages=2),
        _make_search_result(ads=[_make_ad(id=3)], max_pages=2),
    ]
    mock_client_cls.return_value = mock_client

    listings = scrape_leboncoin()
    assert len(listings) == 3
    assert mock_client.search.call_count == 2


@patch("scraper_lbc.lbc.Client")
def test_scrape_leboncoin_empty_page_breaks(mock_client_cls):
    """Pagination: page 2 returns empty ads → loop breaks."""
    mock_client = MagicMock()
    mock_client.search.side_effect = [
        _make_search_result(ads=[_make_ad(id=1)], max_pages=3),
        _make_search_result(ads=[], max_pages=3),
    ]
    mock_client_cls.return_value = mock_client

    listings = scrape_leboncoin()
    assert len(listings) == 1
    assert mock_client.search.call_count == 2


@patch("scraper_lbc.lbc.Client")
def test_scrape_leboncoin_exception_returns_empty(mock_client_cls):
    """Client.search raises → empty list, no crash."""
    mock_client = MagicMock()
    mock_client.search.side_effect = ConnectionError("network error")
    mock_client_cls.return_value = mock_client

    listings = scrape_leboncoin()
    assert listings == []


@patch("scraper_lbc.lbc.Client")
def test_scrape_leboncoin_bad_ad_skipped(mock_client_cls):
    """One ad fails to parse → skipped, others kept."""
    good_ad = _make_ad(id=1)
    bad_ad = _make_ad(id=2)
    # Make bad_ad.attributes raise when iterated
    bad_ad.attributes = None  # will cause TypeError in _ad_to_listing

    mock_client = MagicMock()
    mock_client.search.return_value = _make_search_result(
        ads=[bad_ad, good_ad], max_pages=1,
    )
    mock_client_cls.return_value = mock_client

    listings = scrape_leboncoin()
    assert len(listings) == 1
    assert listings[0].id == "lbc_1"


@patch("scraper_lbc.lbc.Client")
def test_scrape_leboncoin_search_params(mock_client_cls):
    """Verify search is called with correct kwargs."""
    import lbc as lbc_mod
    mock_client = MagicMock()
    mock_client.search.return_value = _make_search_result(ads=[], max_pages=1)
    mock_client_cls.return_value = mock_client

    scrape_leboncoin()

    mock_client.search.assert_called_once_with(
        category=lbc_mod.Category.VEHICULES_VOITURES,
        u_car_brand=("TOYOTA",),
        u_car_model=("TOYOTA_iQ",),
        gearbox=("2",),
        limit=100,
    )


@patch("scraper_lbc.lbc.Client")
def test_scrape_leboncoin_pagination_error_stops(mock_client_cls):
    """Page 2 raises → stops pagination, returns page 1 results."""
    mock_client = MagicMock()
    mock_client.search.side_effect = [
        _make_search_result(ads=[_make_ad(id=1)], max_pages=3),
        Exception("page 2 error"),
    ]
    mock_client_cls.return_value = mock_client

    listings = scrape_leboncoin()
    assert len(listings) == 1
