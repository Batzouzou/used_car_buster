"""La Centrale scraper with __NEXT_DATA__ JSON extraction + HTML fallback."""
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import SEARCH_CRITERIA, OUTPUT_DIR
from models import RawListing

logger = logging.getLogger(__name__)

LC_BASE_URL = "https://www.lacentrale.fr/listing"

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


def parse_lacentrale_nextdata(html: str) -> list[RawListing]:
    """Parse La Centrale __NEXT_DATA__ JSON from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        return []

    try:
        data = json.loads(script_tag.string)
        raw_listings_data = (
            data.get("props", {})
            .get("pageProps", {})
            .get("searchData", {})
            .get("listings", [])
        )
    except (json.JSONDecodeError, AttributeError):
        return []

    listings = []
    now = datetime.now(timezone.utc).isoformat()

    for item in raw_listings_data:
        try:
            gearbox = (item.get("gearbox") or "").lower()
            transmission = "auto" if "auto" in gearbox else ("manual" if gearbox else None)

            seller_raw = (item.get("sellerType") or "").upper()
            seller_type = "pro" if "PRO" in seller_raw else "private"

            city = item.get("city", "")
            coords = geocode_city(city)
            lat = coords[0] if coords else None
            lon = coords[1] if coords else None

            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = f"https://www.lacentrale.fr{url}"

            listing = RawListing(
                id=f"lc_{item['id']}",
                platform="lacentrale",
                title=item.get("title", ""),
                price=int(item.get("price", 0)),
                year=int(item.get("year", 2009)),
                mileage_km=int(item["mileage"]) if item.get("mileage") else None,
                transmission=transmission,
                fuel=item.get("fuel"),
                city=city,
                department=item.get("department"),
                lat=lat,
                lon=lon,
                seller_type=seller_type,
                url=url,
                description=None,
                images=item.get("images", []),
                scraped_at=now,
            )
            listings.append(listing)
        except Exception as e:
            logger.warning(f"Failed to parse LC listing {item.get('id', '?')}: {e}")

    return listings


def scrape_lacentrale() -> list[RawListing]:
    """Scrape La Centrale for Toyota iQ listings."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html",
        "Accept-Language": "fr-FR,fr;q=0.9",
    })

    all_listings = []
    make = SEARCH_CRITERIA["make"].lower()
    model = SEARCH_CRITERIA["model"].lower()

    try:
        time.sleep(random.uniform(2, 5))
        url = f"{LC_BASE_URL}?makesModelsCommercialNames={make}%3A{model}"
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        all_listings = parse_lacentrale_nextdata(resp.text)
        logger.info(f"La Centrale: scraped {len(all_listings)} listings")
    except Exception as e:
        logger.error(f"La Centrale scrape failed: {e}")

    return all_listings
