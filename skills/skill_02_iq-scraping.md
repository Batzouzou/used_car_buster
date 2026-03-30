---
name: iq-scraping
description: Scraper architecture, anti-detection strategy, fallback chain, output schema, and platform-specific gotchas for LeBonCoin and La Centrale. Load for any scraping, parsing, or HTML extraction task.
version: 1.0
updated: 2026-03-28
load: scraping | lbc | lacentrale | html parsing | anti-detection | fixtures
---

# SKILL 02 — SCRAPING

## Architecture principle

**Scrapers are NOT agents.** Pure deterministic code. No LLM calls inside scrapers.
Input: search URL + criteria. Output: `list[RawListing]` JSON.

## Platforms

| Platform | File | Method | Notes |
|----------|------|--------|-------|
| LeBonCoin | scraper_lbc.py | API → __NEXT_DATA__ → HTML fallback | Aggressive blocking |
| La Centrale | scraper_lacentrale.py | HTML parse | No GPS, city names only |

## LBC fallback chain (in order)

```python
1. LBC internal API (undocumented, may break)
2. __NEXT_DATA__ JSON embedded in page HTML
3. Full HTML parse (BeautifulSoup)
→ If all fail: log error, return partial results, CONTINUE (don't abort)
```

## Anti-detection (mandatory — LBC will block without this)

```python
DELAYS = (2, 5)          # random.uniform(*DELAYS) between requests
USER_AGENTS = [...]      # curated list, rotate per session
SESSION_MANAGEMENT = True  # maintain cookies + referer chain
RETRY_ON = [403, 429]    # exponential backoff: 2s, 4s, 8s, max 3 retries
CACHE_RAW_HTML = True    # save to _IQ/html_cache/ for debug/replay
```

Never use parallel requests to the same platform. Sequential only.

## Output schema (enforced via Pydantic RawListing)

```python
@dataclass
class RawListing:
    id: str                    # "lbc_123456" | "lc_789"
    platform: str              # "leboncoin" | "lacentrale"
    title: str
    price: int                 # EUR — required
    year: int                  # required
    mileage_km: int | None
    transmission: str | None   # "auto" | "manual" | "unknown"
    fuel: str | None
    city: str
    department: str | None
    lat: float | None          # None for La Centrale → geocode
    lon: float | None
    seller_type: str           # "pro" | "private" | "unknown"
    url: str
    description: str | None
    images: list[str]
    scraped_at: str            # ISO 8601
    raw_html_path: str | None  # path to cached HTML
```

## Geocoding (La Centrale)

```python
# 1. Check geocode_cache.json (covers 80% of IDF cities)
# 2. Fallback: Nominatim (OSM) — rate limit 1 req/sec
# 3. If Nominatim down: lat/lon = None, proximity score = 0 (don't crash)
ORLY = (48.7262, 2.3652)
```

## Output files

```
_IQ/raw_listings_YYYYMMDD.json   # all scraped listings (raw, unscored)
_IQ/html_cache/                  # raw HTML cache for replay
```

## Gotchas

- LBC may return manual iQ listings — transmission field not always populated. Let analyst flag as "unknown", not scraper.
- La Centrale search pagination: max 100 results per page. iQ auto total < 20 likely, no pagination issue.
- Price sometimes formatted as "3 200 €" (non-breaking space) — strip and cast to int.
- `mileage_km = None` is valid (seller didn't mention) — not the same as 0.
- Duplicate IDs possible across runs — state.py deduplicates by `platform_id`.
