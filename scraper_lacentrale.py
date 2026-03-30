"""La Centrale scraper — Playwright CDP to existing Chrome + __NEXT_DATA__ extraction.

Requires Chrome running with: chrome.exe --remote-debugging-port=9222
The user must visit lacentrale.fr once manually to establish DataDome cookies.
"""
import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import SEARCH_CRITERIA, OUTPUT_DIR

logger = logging.getLogger(__name__)

LC_BASE_URL = "https://www.lacentrale.fr/listing"
LC_MAX_PAGES = 4
CDP_URL = "http://127.0.0.1:9222"

CITY_COORDS_CACHE = {
    "paris": (48.8566, 2.3522), "creteil": (48.7904, 2.4628),
    "vitry-sur-seine": (48.7874, 2.3928), "ivry-sur-seine": (48.8113, 2.3842),
    "villejuif": (48.7922, 2.3637), "orly": (48.7262, 2.3652),
    "antony": (48.7533, 2.2981), "boulogne-billancourt": (48.8397, 2.2399),
    "nanterre": (48.8924, 2.2071), "versailles": (48.8014, 2.1301),
    "evry": (48.6243, 2.4407), "meaux": (48.9601, 2.8788),
    "lyon": (45.7640, 4.8357), "marseille": (43.2965, 5.3698),
    "toulouse": (43.6047, 1.4442), "bordeaux": (44.8378, -0.5792),
    "lille": (50.6292, 3.0573), "nantes": (47.2184, -1.5536),
    "strasbourg": (48.5734, 7.7521), "rennes": (48.1173, -1.6778),
    "montpellier": (43.6108, 3.8767), "nice": (43.7102, 7.2620),
}


def geocode_city(city: str) -> tuple[float, float] | None:
    """Get GPS coordinates for a city. Cache -> Nominatim fallback."""
    if not city:
        return None

    normalized = city.lower().strip()
    if normalized in CITY_COORDS_CACHE:
        return CITY_COORDS_CACHE[normalized]

    cache_path = Path(OUTPUT_DIR) / "geocode_cache.json"
    disk_cache = {}
    if cache_path.exists():
        try:
            disk_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    if normalized in disk_cache:
        coords = disk_cache[normalized]
        return (coords[0], coords[1])

    try:
        time.sleep(1.1)
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{city}, France", "format": "json", "limit": 1},
            headers={"User-Agent": "ToyotaIQSearch/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
            disk_cache[normalized] = [lat, lon]
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(disk_cache, indent=2), encoding="utf-8")
            return (lat, lon)
    except Exception as e:
        logger.warning(f"Nominatim geocode failed for {city}: {e}")

    return None


def _parse_mileage(text: str) -> int | None:
    """Parse mileage like '63 000 km' → 63000."""
    m = re.search(r"([\d\s]+)\s*km", text, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(" ", "").replace("\xa0", ""))
    return None


def _parse_price(text: str) -> int:
    """Parse price like '6 280 €' → 6280."""
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else 0


def parse_lacentrale_nextdata(html: str) -> list:
    """Parse La Centrale listings from __NEXT_DATA__ HTML content.

    La Centrale embeds an HTML string inside __NEXT_DATA__ JSON at
    props.pageProps.data.content.  Listings are <a data-testid="vehicleCardV2">
    elements with CSS-class-based fields.
    """
    from models import RawListing

    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        return []

    try:
        data = json.loads(script_tag.string)
        content_html = (
            data.get("props", {})
            .get("pageProps", {})
            .get("data", {})
            .get("content", "")
        )
    except (json.JSONDecodeError, AttributeError):
        return []

    if not content_html:
        return []

    content_soup = BeautifulSoup(content_html, "html.parser")
    cards = content_soup.find_all("a", attrs={"data-testid": "vehicleCardV2"})

    listings = []
    seen_ids = set()
    now = datetime.now(timezone.utc).isoformat()

    for card in cards:
        try:
            href = card.get("href", "")
            m = re.search(r"annonce-(\d+)", href)
            if not m:
                continue
            raw_id = m.group(1)
            if raw_id in seen_ids:
                continue
            seen_ids.add(raw_id)

            _find = lambda pat: card.find(class_=lambda c: c and pat in c)

            title_el = _find("title__")
            subtitle_el = _find("subTitle__")
            price_el = _find("vehiclePrice__")
            seller_el = _find("vehiclecardV2_seller__")
            loc_el = _find("locationText__")

            title_text = title_el.get_text(strip=True) if title_el else ""
            subtitle_text = subtitle_el.get_text(strip=True) if subtitle_el else ""
            full_title = f"{title_text} {subtitle_text}".strip()

            price = _parse_price(price_el.get_text(strip=True)) if price_el else 0

            # Specs: year, transmission, mileage, fuel from characteristicsItem elements
            spec_els = card.find_all(
                class_=lambda c: c and "vehicleCharacteristicsItem__" in c
            )
            specs = [s.get_text(strip=True) for s in spec_els]

            year = None
            transmission = None
            mileage_km = None
            fuel = None
            for sp in specs:
                if re.match(r"^\d{4}$", sp):
                    year = int(sp)
                elif "km" in sp.lower():
                    mileage_km = _parse_mileage(sp)
                elif sp.lower() in ("auto", "automatique"):
                    transmission = "auto"
                elif sp.lower() in ("manuelle", "manual"):
                    transmission = "manual"
                elif sp.lower() in ("essence", "diesel", "hybride", "electrique", "électrique", "gpl"):
                    fuel = sp.lower()

            seller_name = seller_el.get_text(strip=True) if seller_el else ""
            seller_type = "pro" if seller_name else "private"

            department = loc_el.get_text(strip=True) if loc_el else ""

            url = href if href.startswith("http") else f"https://www.lacentrale.fr{href}"

            listing = RawListing(
                id=f"lc_{raw_id}",
                platform="lacentrale",
                title=full_title,
                price=price,
                year=year or 2009,
                mileage_km=mileage_km,
                transmission=transmission,
                fuel=fuel,
                city=department,
                department=department,
                lat=None,
                lon=None,
                seller_type=seller_type,
                url=url,
                description=None,
                images=[],
                scraped_at=now,
            )
            listings.append(listing)
        except Exception as e:
            logger.warning(f"Failed to parse LC card: {e}")

    return listings


# ---------------------------------------------------------------------------
# Human-like browser helpers
# ---------------------------------------------------------------------------

def _human_wiggle(page) -> None:
    """Random mouse movement to mimic human behavior."""
    x = random.randint(120, 900)
    y = random.randint(120, 700)
    page.mouse.move(x, y, steps=random.randint(6, 14))
    time.sleep(random.uniform(0.08, 0.22))


def _human_scroll(page, times: int | None = None) -> None:
    """Random scroll to mimic browsing."""
    n = times if times is not None else random.randint(2, 4)
    for _ in range(n):
        page.mouse.wheel(0, random.randint(250, 700))
        time.sleep(random.uniform(0.3, 0.7))


def _is_block_page(html: str) -> bool:
    """Detect DataDome/captcha block pages."""
    low = (html or "").lower()
    return any(marker in low for marker in [
        "captcha", "datadome", "you've been blocked",
        "access blocked", "please enable js",
    ])


def _polite_sleep(lo: float = 1.5, hi: float = 3.2) -> None:
    time.sleep(random.uniform(lo, hi))


# ---------------------------------------------------------------------------
# Main scraper — CDP approach
# ---------------------------------------------------------------------------

def scrape_lacentrale() -> list:
    """Scrape La Centrale via Playwright CDP connection to existing Chrome.

    Requires Chrome running with --remote-debugging-port=9222.
    Falls back to empty list if Chrome not available or page blocked.
    """
    from models import RawListing

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("La Centrale: playwright not installed, skipping")
        return []

    make = SEARCH_CRITERIA["make"].lower()
    model = SEARCH_CRITERIA["model"].lower()
    # Note: &gearbox=Automatique breaks SSR (empty results), so we post-filter
    base_url = f"{LC_BASE_URL}?makesModelsCommercialNames={make}%3A{model}"

    all_listings = []
    seen_ids = set()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.new_page()

            try:
                for page_num in range(1, LC_MAX_PAGES + 1):
                    url = base_url if page_num == 1 else f"{base_url}&page={page_num}"

                    _polite_sleep(1.0, 2.5)
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    _polite_sleep(3.0, 5.0)

                    _human_wiggle(page)
                    _human_scroll(page, times=2)
                    _polite_sleep(1.0, 2.0)

                    html = page.content()

                    if _is_block_page(html):
                        logger.warning("La Centrale: DataDome block detected, stopping pagination")
                        break

                    nextdata_len = page.evaluate(
                        'document.getElementById("__NEXT_DATA__")?.textContent?.length || 0'
                    )
                    if nextdata_len == 0:
                        logger.info(f"La Centrale: no __NEXT_DATA__ on page {page_num}, done")
                        break

                    raw = parse_lacentrale_nextdata(html)
                    if not raw:
                        logger.info(f"La Centrale: 0 listings on page {page_num}, done")
                        break

                    new_count = 0
                    for listing in raw:
                        if listing.id not in seen_ids:
                            seen_ids.add(listing.id)
                            all_listings.append(listing)
                            new_count += 1

                    logger.info(f"La Centrale page {page_num}: {len(raw)} cards, {new_count} new")

                    if new_count == 0:
                        break

                # Post-filter by transmission
                target_trans = SEARCH_CRITERIA.get("transmission", "").lower()
                if target_trans == "automatic":
                    before = len(all_listings)
                    all_listings = [l for l in all_listings if l.transmission == "auto"]
                    logger.info(
                        f"La Centrale: {before} total, {len(all_listings)} automatic via CDP"
                    )
                else:
                    logger.info(f"La Centrale: {len(all_listings)} listings via CDP")

            finally:
                page.close()

    except Exception as e:
        err_msg = str(e)
        if "connect" in err_msg.lower() or "refused" in err_msg.lower():
            logger.warning(
                "La Centrale: Chrome CDP not available on port 9222. "
                "Start Chrome with: chrome.exe --remote-debugging-port=9222"
            )
        else:
            logger.error(f"La Centrale scrape failed: {e}")

    return all_listings
