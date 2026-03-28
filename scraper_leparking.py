"""Le Parking scraper — HTML parsing for aggregator site."""
import logging
import random
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import SEARCH_CRITERIA
from models import RawListing
from scraper_lacentrale import geocode_city

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
]

LP_SEARCH_URL = "https://www.leparking.fr/voiture-occasion/toyota-iq.html"


def _parse_price(text: str) -> int:
    """Extract integer price from text like '3 200 EUR' or '3200€'."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def _parse_mileage(text: str) -> int | None:
    """Extract mileage from text like '78 000 km'."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_year(text: str) -> int:
    """Extract year from text."""
    match = re.search(r"(20\d{2}|19\d{2})", text)
    return int(match.group(1)) if match else 2009


def parse_leparking_html(html: str) -> list[RawListing]:
    """Parse Le Parking search results HTML into RawListing models."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".vehicle-card")

    listings = []
    now = datetime.now(timezone.utc).isoformat()

    for card in cards:
        try:
            card_id = card.get("data-id", "")

            link_tag = card.find("a", href=True)
            url = ""
            if link_tag:
                href = link_tag["href"]
                url = f"https://www.leparking.fr{href}" if not href.startswith("http") else href

            img_tag = card.find("img")
            images = [img_tag["src"]] if img_tag and img_tag.get("src") else []

            title_tag = card.find("h2")
            title = title_tag.get_text(strip=True) if title_tag else ""

            price_tag = card.select_one(".price")
            price = _parse_price(price_tag.get_text()) if price_tag else 0

            year_tag = card.select_one(".year")
            year = _parse_year(year_tag.get_text()) if year_tag else 2009

            mileage_tag = card.select_one(".mileage")
            mileage_km = _parse_mileage(mileage_tag.get_text()) if mileage_tag else None

            fuel_tag = card.select_one(".fuel")
            fuel = fuel_tag.get_text(strip=True) if fuel_tag else None

            location_tag = card.select_one(".location")
            location_text = location_tag.get_text(strip=True) if location_tag else ""
            # Extract city (before parenthesis)
            city_match = re.match(r"([^(]+)", location_text)
            city = city_match.group(1).strip() if city_match else location_text
            dept_match = re.search(r"\((\d+)\)", location_text)
            department = dept_match.group(1) if dept_match else None

            coords = geocode_city(city)
            lat = coords[0] if coords else None
            lon = coords[1] if coords else None

            seller_tag = card.select_one(".seller-type")
            seller_text = (seller_tag.get_text(strip=True) if seller_tag else "").lower()
            seller_type = "pro" if "pro" in seller_text else "private"

            listing = RawListing(
                id=f"lp_{card_id}",
                platform="leparking",
                title=title,
                price=price,
                year=year,
                mileage_km=mileage_km,
                transmission=None,  # Le Parking doesn't reliably show transmission
                fuel=fuel,
                city=city,
                department=department,
                lat=lat,
                lon=lon,
                seller_type=seller_type,
                url=url,
                description=None,
                images=images,
                scraped_at=now,
            )
            listings.append(listing)
        except Exception as e:
            logger.warning(f"Failed to parse Le Parking card {card.get('data-id', '?')}: {e}")

    return listings


def scrape_leparking() -> list[RawListing]:
    """Scrape Le Parking for Toyota iQ listings."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html",
        "Accept-Language": "fr-FR,fr;q=0.9",
    })

    all_listings = []

    try:
        time.sleep(random.uniform(2, 5))
        resp = session.get(LP_SEARCH_URL, timeout=30)
        resp.raise_for_status()
        all_listings = parse_leparking_html(resp.text)
        logger.info(f"Le Parking: scraped {len(all_listings)} listings")
    except Exception as e:
        logger.error(f"Le Parking scrape failed: {e}")

    return all_listings
