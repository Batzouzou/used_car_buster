"""LeBonCoin scraper with API + fallback chain."""
import logging
import random
import time
from datetime import datetime, timezone

import requests

from config import SEARCH_CRITERIA
from models import RawListing

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
]

LBC_API_URL = "https://api.leboncoin.fr/finder/search"
LBC_GEARBOX_MAP = {"1": "manual", "2": "auto"}


def _build_lbc_params() -> dict:
    return {
        "category": "2",
        "text": f"{SEARCH_CRITERIA['make']} {SEARCH_CRITERIA['model']}",
        "price": {"min": 0, "max": SEARCH_CRITERIA["max_price"]},
        "mileage": {"min": 0, "max": SEARCH_CRITERIA["max_mileage_km"]},
        "vehicle_vdate": {"min": SEARCH_CRITERIA["min_year"]},
        "limit": 100,
        "offset": 0,
    }


def _get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.leboncoin.fr",
        "Referer": "https://www.leboncoin.fr/",
        "api_key": "ba0c2dad52b3ec",
    })
    return session


def parse_lbc_listings(ads: list[dict]) -> list[RawListing]:
    """Parse LBC API ad objects into RawListing models."""
    listings = []
    now = datetime.now(timezone.utc).isoformat()

    for ad in ads:
        try:
            attrs = {a["key"]: a.get("value") for a in ad.get("attributes", [])}
            location = ad.get("location", {})
            owner = ad.get("owner", {})
            images_data = ad.get("images", {})
            image_urls = images_data.get("urls", []) if isinstance(images_data, dict) else []

            gearbox_raw = attrs.get("gearbox", "")
            transmission = LBC_GEARBOX_MAP.get(str(gearbox_raw))

            mileage = attrs.get("mileage")
            mileage_km = int(mileage) if mileage else None

            year_raw = attrs.get("regdate")
            year = int(year_raw) if year_raw else 2009

            price_list = ad.get("price", [0])
            price = price_list[0] if price_list else 0

            seller_type = "pro" if owner.get("type") == "pro" else "private"

            listing = RawListing(
                id=f"lbc_{ad['list_id']}",
                platform="leboncoin",
                title=ad.get("subject", ""),
                price=price,
                year=year,
                mileage_km=mileage_km,
                transmission=transmission,
                fuel=attrs.get("fuel"),
                city=location.get("city"),
                department=location.get("department_id"),
                lat=location.get("lat"),
                lon=location.get("lng"),
                seller_type=seller_type,
                url=ad.get("url", ""),
                description=ad.get("body"),
                images=image_urls,
                scraped_at=now,
            )
            listings.append(listing)
        except Exception as e:
            logger.warning(f"Failed to parse LBC ad {ad.get('list_id', '?')}: {e}")

    return listings


def scrape_leboncoin() -> list[RawListing]:
    """Scrape LeBonCoin for Toyota iQ listings."""
    session = _get_session()
    all_listings = []

    try:
        params = _build_lbc_params()
        time.sleep(random.uniform(2, 5))

        resp = session.post(LBC_API_URL, json=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        ads = data.get("ads", [])
        all_listings = parse_lbc_listings(ads)
        logger.info(f"LBC: scraped {len(all_listings)} listings")

        total = data.get("total", 0)
        offset = len(ads)
        while offset < total:
            time.sleep(random.uniform(2, 5))
            params["offset"] = offset
            resp = session.post(LBC_API_URL, json=params, timeout=30)
            resp.raise_for_status()
            page_data = resp.json()
            page_ads = page_data.get("ads", [])
            if not page_ads:
                break
            all_listings.extend(parse_lbc_listings(page_ads))
            offset += len(page_ads)

    except requests.exceptions.HTTPError as e:
        if e.response and e.response.status_code in (403, 429):
            logger.warning(f"LBC blocked ({e.response.status_code}), trying fallback")
            all_listings = _scrape_lbc_fallback(session)
        else:
            logger.error(f"LBC HTTP error: {e}")
    except Exception as e:
        logger.error(f"LBC scrape failed: {e}")

    return all_listings


def _scrape_lbc_fallback(session: requests.Session) -> list[RawListing]:
    """Fallback: scrape LBC via HTML / __NEXT_DATA__ JSON."""
    logger.info("LBC fallback: attempting HTML scrape")
    logger.warning("LBC HTML fallback not yet implemented")
    return []
