"""LeBonCoin scraper using lbc library (curl-cffi TLS bypass)."""
import logging
from datetime import datetime, timezone

import lbc

from config import SEARCH_CRITERIA
from models import RawListing

logger = logging.getLogger(__name__)

LBC_GEARBOX_MAP = {"1": "manual", "2": "auto"}


def _ad_to_listing(ad: lbc.Ad) -> RawListing:
    """Convert a lbc.Ad dataclass to our RawListing model."""
    now = datetime.now(timezone.utc).isoformat()

    attrs = {a.key: a.value for a in ad.attributes}

    gearbox_raw = attrs.get("gearbox", "")
    transmission = LBC_GEARBOX_MAP.get(str(gearbox_raw))

    mileage = attrs.get("mileage")
    mileage_km = int(mileage) if mileage else None

    year_raw = attrs.get("regdate")
    year = int(year_raw) if year_raw else 2009

    seller_type = "pro" if ad.ad_type == "pro" else "private"

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
        result = client.search(
            category=lbc.Category.VEHICULES_VOITURES,
            u_car_brand=("TOYOTA",),
            u_car_model=("TOYOTA_iQ",),
            gearbox=("2",),
            limit=100,
        )

        for ad in result.ads:
            try:
                listing = _ad_to_listing(ad)
                all_listings.append(listing)
            except Exception as e:
                logger.warning(f"Failed to parse LBC ad {ad.id}: {e}")

        logger.info(f"LBC: scraped {len(all_listings)} listings")

        # Pagination: fetch remaining pages
        page = 2
        while page <= result.max_pages:
            try:
                result = client.search(
                    category=lbc.Category.VEHICULES_VOITURES,
                    u_car_brand=("TOYOTA",),
                    u_car_model=("TOYOTA_iQ",),
                    gearbox=("2",),
                    limit=100,
                    page=page,
                )
                if not result.ads:
                    break
                for ad in result.ads:
                    try:
                        all_listings.append(_ad_to_listing(ad))
                    except Exception as e:
                        logger.warning(f"Failed to parse LBC ad {ad.id}: {e}")
                page += 1
            except Exception as e:
                logger.warning(f"LBC pagination page {page} failed: {e}")
                break

    except Exception as e:
        logger.error(f"LBC scrape failed: {e}")

    return all_listings
