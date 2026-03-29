"""LeBonCoin scraper using lbc library (curl-cffi TLS bypass)."""
import logging
from datetime import datetime, timezone

import lbc

from config import SEARCH_CRITERIA
from models import RawListing

logger = logging.getLogger(__name__)

LBC_GEARBOX_MAP = {"1": "manual", "2": "auto"}

# Keywords in ad body that indicate a professional seller despite "private" account
PRO_KEYWORDS = ["frais d'agence", "frais d agence", "siret", "professionnel", "garantie constructeur"]

# Jerome's actual LBC search URL — location centered on Athis-Mons (near Orly), 200km radius
LBC_SEARCH_URL = (
    "https://www.leboncoin.fr/recherche?"
    "category=2"
    "&locations=Athis-Mons_91200__48.70773_2.38881_2665_200000"
    "&u_car_brand=TOYOTA"
    "&u_car_model=TOYOTA_iQ"
    "&gearbox=2"
)


def _detect_suspected_pro(body: str | None) -> bool:
    """Detect if a 'private' seller is actually a pro based on body keywords."""
    if not body:
        return False
    body_lower = body.lower()
    return any(kw in body_lower for kw in PRO_KEYWORDS)


def _ad_to_listing(ad: lbc.Ad) -> RawListing | None:
    """Convert a lbc.Ad dataclass to our RawListing model.

    Returns None for non-auto transmission (post-filter).
    """
    now = datetime.now(timezone.utc).isoformat()

    attrs = {a.key: a.value for a in ad.attributes}

    gearbox_raw = attrs.get("gearbox", "")
    transmission = LBC_GEARBOX_MAP.get(str(gearbox_raw))

    # Fix #1: post-filter — exclude non-auto even if LBC miscategorized
    if transmission and transmission != "auto":
        logger.info(f"LBC: excluded ad {ad.id} — transmission={transmission}")
        return None

    mileage = attrs.get("mileage")
    mileage_km = int(mileage) if mileage else None

    year_raw = attrs.get("regdate")
    year = int(year_raw) if year_raw else 2009

    # Fix #2 + #3: seller_type from user.is_pro + suspected_pro
    is_pro_api = getattr(getattr(ad, "user", None), "is_pro", False)
    suspected_pro = _detect_suspected_pro(ad.body)
    seller_type = "pro" if (is_pro_api or suspected_pro) else "private"

    # Fix #4: has_phone indicator
    has_phone = getattr(ad, "has_phone", False)

    return RawListing(
        id=f"lbc_{ad.id}",
        platform="leboncoin",
        title=ad.subject or "",
        price=int(ad.price) if ad.price else 0,
        year=year,
        mileage_km=mileage_km,
        transmission=transmission,
        fuel=attrs.get("fuel"),
        city=ad.location.city if ad.location else None,
        department=ad.location.department_id if ad.location else None,
        lat=ad.location.lat if ad.location else None,
        lon=ad.location.lng if ad.location else None,
        seller_type=seller_type,
        suspected_pro=suspected_pro,
        has_phone=has_phone,
        url=ad.url or "",
        description=ad.body,
        images=ad.images or [],
        scraped_at=now,
    )


def scrape_leboncoin() -> list[RawListing]:
    """Scrape LeBonCoin for Toyota iQ listings using lbc library."""
    all_listings: list[RawListing] = []

    try:
        client = lbc.Client()
        result = client.search(url=LBC_SEARCH_URL, limit=100)
        logger.info(f"LBC: max_pages={result.max_pages}, first page ads={len(result.ads)}")

        for ad in result.ads:
            try:
                listing = _ad_to_listing(ad)
                if listing is not None:
                    all_listings.append(listing)
            except Exception as e:
                logger.warning(f"Failed to parse LBC ad {ad.id}: {e}")

        logger.info(f"LBC: scraped {len(all_listings)} listings")

        # Pagination: fetch remaining pages
        page = 2
        while page <= result.max_pages:
            try:
                result = client.search(url=LBC_SEARCH_URL, limit=100, page=page)
                if not result.ads:
                    break
                for ad in result.ads:
                    try:
                        listing = _ad_to_listing(ad)
                        if listing is not None:
                            all_listings.append(listing)
                    except Exception as e:
                        logger.warning(f"Failed to parse LBC ad {ad.id}: {e}")
                page += 1
            except Exception as e:
                logger.warning(f"LBC pagination page {page} failed: {e}")
                break

    except Exception as e:
        logger.error(f"LBC scrape failed: {e}")

    return all_listings
