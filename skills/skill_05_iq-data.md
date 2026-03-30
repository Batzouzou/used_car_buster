---
name: iq-data
description: Pydantic data models, scoring schema, state management, output file conventions, and data flow for the IQ Auto Search system. Load for models.py, state.py, scoring validation, or output file tasks.
version: 1.0
updated: 2026-03-28
load: pydantic | models | state | scoring | data flow | output files | json schema
---

# SKILL 05 — DATA MODELS & STATE

## Design rule

No raw dicts across agent boundaries. All data flows through Pydantic models.
`RawListing` → `ScoredListing` → `PricedListing` is the only valid progression.

## models.py

```python
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime

class RawListing(BaseModel):
    id: str
    platform: str                       # "leboncoin" | "lacentrale"
    title: str
    price: int
    year: int
    mileage_km: Optional[int] = None
    transmission: Optional[str] = None  # "auto" | "manual" | "unknown"
    fuel: Optional[str] = None
    city: str
    department: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    seller_type: str = "unknown"        # "pro" | "private" | "unknown"
    url: str
    description: Optional[str] = None
    images: list[str] = []
    scraped_at: str
    raw_html_path: Optional[str] = None

class ScoreBreakdown(BaseModel):
    price: int
    mileage: int
    year: int
    proximity: int
    condition: int
    transmission: int

class ScoredListing(BaseModel):
    id: str
    raw: RawListing
    score: int                          # -1 = excluded
    score_breakdown: ScoreBreakdown
    excluded: bool
    exclusion_reason: Optional[str] = None
    red_flags: list[str] = []
    highlights: list[str] = []
    concerns: list[str] = []
    estimated_market_value: dict        # {"low": int, "high": int}
    summary_fr: str

    @validator("score")
    def validate_score(cls, v):
        if v != -1 and not (0 <= v <= 100):
            raise ValueError(f"Score must be 0-100 or -1 (excluded), got {v}")
        return v

class PricedListing(BaseModel):
    id: str
    scored: ScoredListing
    estimated_value: dict               # {"low": int, "high": int, "fair": int}
    recommended_offer: int
    negotiation_range: dict             # {"min": int, "max": int}
    nego_message_fr: str
    priced_at: str                      # ISO 8601
```

## State management — state.py

State file: `_IQ/state.json`

```python
DEFAULT_STATE = {
    "version": 1,
    "last_scrape": None,            # ISO 8601 or None
    "raw_listings_file": None,      # path to latest raw JSON
    "scored_listings_file": None,   # path to latest scored JSON
    "approved_ids": [],             # list of listing IDs approved by human
    "priced_file": None,
    "nego_file": None,
    "scrape_count": 0,
    "analyze_count": 0,
    "session_started": None
}

def read_state() -> dict: ...
def write_state(state: dict): ...
def is_data_fresh(max_age_hours: int = 24) -> bool: ...
```

## Output file conventions

```
_IQ/raw_listings_YYYYMMDD.json          # list[RawListing]
_IQ/shortlist_pro_YYYYMMDD.json         # list[ScoredListing] — pro sellers, excluded=False
_IQ/shortlist_part_YYYYMMDD.json        # list[ScoredListing] — private sellers
_IQ/shortlist_approved_YYYYMMDD.json    # human-approved subset
_IQ/priced_YYYYMMDD.json                # list[PricedListing]
_IQ/nego_messages_YYYYMMDD.json         # flat dict: {id: nego_message_fr}
_IQ/geocode_cache.json                  # {city: {lat, lon}} — persistent
_IQ/html_cache/                         # raw HTML per platform+date
```

## Distance utility (utils.py)

```python
from math import radians, sin, cos, sqrt, atan2

ORLY = (48.7262, 2.3652)

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

def orly_distance_score(lat, lon) -> int:
    if lat is None or lon is None:
        return 0
    d = haversine_km(*ORLY, lat, lon)
    if d < 20: return 15
    if d < 30: return 8
    if d < 40: return 3
    return 0
```

## Data validation gate (before dispatch_analyst)

```python
def validate_raw_batch(listings: list[RawListing]) -> tuple[bool, str]:
    if len(listings) == 0:
        return False, "Empty batch — no listings scraped"
    ids = [l.id for l in listings]
    if len(ids) != len(set(ids)):
        return False, f"Duplicate IDs detected"
    missing_price = [l.id for l in listings if l.price <= 0]
    if missing_price:
        return False, f"Missing price on: {missing_price}"
    return True, "OK"
```
