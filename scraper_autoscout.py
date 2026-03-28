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
    """Extract year from firstRegistration like '01/2011' or '2011'."""
    match = re.search(r"(20\d{2}|19\d{2})", first_reg or "")
    return int(match.group(1)) if match else 2009


def parse_autoscout_listings(listings_data: list[dict]) -> list[RawListing]:
    """Parse AutoScout24 listing objects into RawListing models."""
    listings = []
    now = datetime.now(timezone.utc).isoformat()

    for item in listings_data:
        try:
            location = item.get("location", {})

            gear = (item.get("gearType") or "").lower()
            transmission = "auto" if "auto" in gear else ("manual" if gear else None)

            # D = dealer (pro), P = private
            seller_raw = item.get("sellerType", "")
            seller_type = "pro" if seller_raw == "D" else "private"

            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = f"https://www.autoscout24.fr{url}"

            listing = RawListing(
                id=f"as_{item['id']}",
                platform="autoscout24",
                title=item.get("title", ""),
                price=int(item.get("price", 0)),
                year=_extract_year(item.get("firstRegistration")),
                mileage_km=int(item["mileage"]) if item.get("mileage") else None,
                transmission=transmission,
                fuel=item.get("fuelType"),
                city=location.get("city"),
                department=None,
                lat=location.get("latitude"),
                lon=location.get("longitude"),
                seller_type=seller_type,
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
