# tests/test_scraper_lbc.py
"""Tests for LeBonCoin scraper (lbc library integration)."""
import pytest
from dataclasses import dataclass
from unittest.mock import patch, MagicMock
from scraper_lbc import _ad_to_listing, _detect_suspected_pro, scrape_leboncoin
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


def _make_user(is_pro=False):
    user = MagicMock()
    user.is_pro = is_pro
    return user


def _make_ad(**overrides):
    """Create a mock lbc.Ad with sensible defaults."""
    defaults = dict(
        id=12345,
        subject="Toyota iQ 1.33 CVT Automatique",
        price=3200,
        body="Toyota iQ automatique, bon etat, CT OK",
        ad_type="pro",
        has_phone=False,
        url="https://www.leboncoin.fr/voitures/12345.htm",
        images=["https://img.lbc.fr/1.jpg"],
        location=_make_location(),
        user=_make_user(is_pro=False),
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
    assert listing.city == "Vitry-sur-Seine"
    assert listing.lat == 48.787
    assert listing.lon == 2.392


def test_ad_to_listing_private_seller():
    ad = _make_ad(user=_make_user(is_pro=False))
    listing = _ad_to_listing(ad)
    assert listing.seller_type == "private"


# --- Fix #1: post-filter transmission ---

def test_ad_to_listing_manual_gearbox_returns_none():
    """Manual transmission must be post-filtered out (returns None)."""
    ad = _make_ad(attributes=[
        _make_attribute("gearbox", "1"),
        _make_attribute("regdate", "2010"),
    ])
    listing = _ad_to_listing(ad)
    assert listing is None


def test_ad_to_listing_unknown_gearbox_passes():
    """Unknown gearbox (not in map) should pass through, not be filtered."""
    ad = _make_ad(attributes=[
        _make_attribute("gearbox", "99"),
        _make_attribute("regdate", "2010"),
    ])
    listing = _ad_to_listing(ad)
    assert listing is not None
    assert listing.transmission is None


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
def test_scrape_leboncoin_search_uses_url(mock_client_cls):
    """Verify search is called with URL-based params."""
    from scraper_lbc import LBC_SEARCH_URL
    mock_client = MagicMock()
    mock_client.search.return_value = _make_search_result(ads=[], max_pages=1)
    mock_client_cls.return_value = mock_client

    scrape_leboncoin()

    mock_client.search.assert_called_once_with(url=LBC_SEARCH_URL, limit=100)


@patch("scraper_lbc.lbc.Client")
def test_scrape_leboncoin_filters_manual(mock_client_cls):
    """Manual gearbox ads in search results are filtered out."""
    auto_ad = _make_ad(id=1)
    manual_ad = _make_ad(id=2, attributes=[
        _make_attribute("gearbox", "1"),
        _make_attribute("regdate", "2010"),
    ])
    mock_client = MagicMock()
    mock_client.search.return_value = _make_search_result(
        ads=[auto_ad, manual_ad], max_pages=1,
    )
    mock_client_cls.return_value = mock_client

    listings = scrape_leboncoin()
    assert len(listings) == 1
    assert listings[0].id == "lbc_1"


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


# --- Fix #2: _detect_suspected_pro ---

def test_detect_suspected_pro_frais_agence():
    assert _detect_suspected_pro("Prix TTC + frais d'agence 300 EUR") is True


def test_detect_suspected_pro_siret():
    assert _detect_suspected_pro("SIRET 123 456 789 00012") is True


def test_detect_suspected_pro_case_insensitive():
    assert _detect_suspected_pro("FRAIS D'AGENCE inclus") is True


def test_detect_suspected_pro_normal_private():
    assert _detect_suspected_pro("Vends ma Toyota iQ, bon etat") is False


def test_detect_suspected_pro_none_body():
    assert _detect_suspected_pro(None) is False


def test_detect_suspected_pro_empty_body():
    assert _detect_suspected_pro("") is False


# --- Fix #3: seller_type from user.is_pro + suspected_pro ---

def test_seller_type_user_is_pro():
    """user.is_pro=True → seller_type='pro' regardless of body."""
    ad = _make_ad(body="Vends ma voiture", user=_make_user(is_pro=True))
    listing = _ad_to_listing(ad)
    assert listing.seller_type == "pro"


def test_seller_type_suspected_pro_from_body():
    """Private account but body contains 'frais d'agence' → pro + suspected_pro."""
    ad = _make_ad(body="Prix + frais d'agence", user=_make_user(is_pro=False))
    listing = _ad_to_listing(ad)
    assert listing.seller_type == "pro"
    assert listing.suspected_pro is True


def test_seller_type_genuine_private():
    """Private account, clean body → seller_type='private'."""
    ad = _make_ad(body="Vends ma Toyota iQ", user=_make_user(is_pro=False))
    listing = _ad_to_listing(ad)
    assert listing.seller_type == "private"
    assert listing.suspected_pro is False


# --- Fix #4: has_phone ---

def test_has_phone_true():
    ad = _make_ad(has_phone=True)
    listing = _ad_to_listing(ad)
    assert listing.has_phone is True


def test_has_phone_false():
    ad = _make_ad(has_phone=False)
    listing = _ad_to_listing(ad)
    assert listing.has_phone is False
