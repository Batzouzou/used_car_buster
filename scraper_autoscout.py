"""AutoScout24 scraper with __NEXT_DATA__ JSON extraction."""
import json
import logging
import random
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import SEARCH_CRITERIA
from models import RawListing

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
]

AS_SEARCH_URL = "https://www.autoscout24.fr/lst/toyota/iq"


def _extract_year(first_reg: str) -> int:
    """Extract year from firstRegistration like '01/2011', '10-2009', or '2011'."""
    match = re.search(r"(20\d{2}|19\d{2})", first_reg or "")
    return int(match.group(1)) if match else 2009


def _extract_price(price_raw) -> int:
    """Extract price int from old format (int) or new format (dict)."""
    if isinstance(price_raw, (int, float)):
        return int(price_raw)
    if isinstance(price_raw, dict):
        # New format: try tracking.price first (clean int string), else parse formatted
        formatted = price_raw.get("priceFormatted", "")
        digits = re.sub(r"[^\d]", "", formatted)
        return int(digits) if digits else 0
    return int(price_raw) if price_raw else 0


def _extract_mileage(item: dict) -> int | None:
    """Extract mileage from old format (top-level int) or new format (vehicle.mileageInKm)."""
    # Old format: item["mileage"] is an int
    mileage_raw = item.get("mileage")
    if isinstance(mileage_raw, (int, float)):
        return int(mileage_raw)
    # New format: vehicle.mileageInKm is a string like "46 000 km"
    vehicle = item.get("vehicle", {})
    mileage_str = vehicle.get("mileageInKm", "")
    if mileage_str:
        digits = re.sub(r"[^\d]", "", mileage_str)
        return int(digits) if digits else None
    # Fallback: tracking.mileage as clean int string
    tracking = item.get("tracking", {})
    track_km = tracking.get("mileage")
    if track_km:
        return int(track_km)
    return None


def _extract_transmission(item: dict) -> str | None:
    """Extract transmission from old or new format."""
    # Old format: item["gearType"]
    gear = item.get("gearType", "")
    if not gear:
        # New format: vehicle.transmission
        vehicle = item.get("vehicle", {})
        gear = vehicle.get("transmission", "")
    gear_lower = gear.lower()
    if "auto" in gear_lower:
        return "auto"
    if "manuel" in gear_lower or "manual" in gear_lower:
        return "manual"
    return None if not gear_lower else None


def _extract_seller_type(item: dict) -> str:
    """Extract seller type from old or new format."""
    # Old format: sellerType = "D" or "P"
    seller_raw = item.get("sellerType", "")
    if seller_raw == "D":
        return "pro"
    if seller_raw == "P":
        return "private"
    # New format: seller.type = "Dealer" or "Private"
    seller = item.get("seller", {})
    seller_type = seller.get("type", "")
    if seller_type.lower() == "dealer":
        return "pro"
    return "private"


def _extract_seller_name(item: dict) -> str | None:
    """Extract seller/contact name from old or new format."""
    seller = item.get("seller", {})
    return seller.get("contactName") or seller.get("companyName") or None


def _extract_seller_phone(item: dict) -> str | None:
    """Extract seller phone from new format (phones array)."""
    seller = item.get("seller", {})
    phones = seller.get("phones", [])
    if phones:
        return phones[0].get("callTo") or phones[0].get("formattedNumber")
    return None


def _extract_title(item: dict) -> str:
    """Extract title from old or new format."""
    title = item.get("title", "")
    if not title:
        vehicle = item.get("vehicle", {})
        title = vehicle.get("subtitle") or f"{vehicle.get('make', '')} {vehicle.get('model', '')}".strip()
    return title


def parse_autoscout_listings(listings_data: list[dict]) -> list[RawListing]:
    """Parse AutoScout24 listing objects into RawListing models.

    Supports both old format (flat keys) and new 2026 format (nested vehicle/seller/tracking).
    """
    listings = []
    now = datetime.now(timezone.utc).isoformat()

    for item in listings_data:
        try:
            location = item.get("location", {})
            tracking = item.get("tracking", {})

            # Year: old firstRegistration at top level, new in tracking
            first_reg = item.get("firstRegistration") or tracking.get("firstRegistration", "")

            # Fuel: old fuelType at top level, new in vehicle
            vehicle = item.get("vehicle", {})
            fuel = item.get("fuelType") or vehicle.get("fuel")

            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = f"https://www.autoscout24.fr{url}"

            listing = RawListing(
                id=f"as_{item['id']}",
                platform="autoscout24",
                title=_extract_title(item),
                price=_extract_price(item.get("price", 0)),
                year=_extract_year(first_reg),
                mileage_km=_extract_mileage(item),
                transmission=_extract_transmission(item),
                fuel=fuel,
                city=location.get("city"),
                department=None,
                lat=location.get("latitude"),
                lon=location.get("longitude"),
                seller_type=_extract_seller_type(item),
                seller_name=_extract_seller_name(item),
                seller_phone=_extract_seller_phone(item),
                url=url,
                description=None,
                images=item.get("images", []),
                scraped_at=now,
            )
            listings.append(listing)
        except Exception as e:
            logger.warning(f"Failed to parse AutoScout listing {item.get('id', '?')}: {e}")

    return listings


def scrape_autoscout24() -> list[RawListing]:
    """Scrape AutoScout24 for Toyota iQ listings."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html",
        "Accept-Language": "fr-FR,fr;q=0.9",
    })

    all_listings = []

    try:
        time.sleep(random.uniform(2, 5))
        resp = session.get(AS_SEARCH_URL, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if not script_tag or not script_tag.string:
            logger.warning("AutoScout24: no __NEXT_DATA__ found")
            return []

        data = json.loads(script_tag.string)
        listings_data = (
            data.get("props", {})
            .get("pageProps", {})
            .get("listings", [])
        )
        all_listings = parse_autoscout_listings(listings_data)
        logger.info(f"AutoScout24: scraped {len(all_listings)} listings")
    except Exception as e:
        logger.error(f"AutoScout24 scrape failed: {e}")

    return all_listings
