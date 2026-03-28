"""Analyst agent: scores listings against weighted rubric via LLM."""
import json
import logging
from models import RawListing, ScoredListing, ScoreBreakdown
from llm_client import LLMClient
from utils import extract_json_from_text

logger = logging.getLogger(__name__)

ANALYST_SYSTEM_PROMPT = """You are a used car analyst specializing in the French market.

TASK: Score each Toyota iQ listing against the buyer's criteria.
Output a JSON ARRAY of objects, one per listing, with the exact schema below.

SCORING RUBRIC (100 points total):
- Price (30 pts): 5000€=0, 4000€=15, 3000€=25, <2500€=30
- Mileage (20 pts): 150k=0, 100k=10, 70k=15, <50k=20
- Year (15 pts): 2009=5, 2011=10, 2013+=15
- Proximity to Orly (15 pts): <20km=15, 20-30km=8, 30-40km=3, >40km=0
- Condition signals (10 pts, CAPPED at 10): "en l'etat"=-10, "accident"=-10, "CT OK"=+5, "carnet entretien"=+5, "1 proprietaire"=+5
- Transmission confirmed auto (10 pts): confirmed=10, unclear=0, manual=EXCLUDE

RED FLAGS (instant exclude or heavy penalty):
- Transmission = manual → EXCLUDE (score = -1)
- Price > 5000€ → EXCLUDE
- Mileage > 150000 km → EXCLUDE
- "en l'etat" / "accidente" / "pour pieces" → score = max 20
- "SIV" / fleet vehicle → -10 pts

OUTPUT SCHEMA (strict JSON array, no markdown, no explanation):
[{
  "id": "lbc_123456",
  "score": 72,
  "score_breakdown": {"price": 25, "mileage": 15, "year": 10, "proximity": 8, "condition": 10, "transmission": 10},
  "excluded": false,
  "exclusion_reason": null,
  "red_flags": [],
  "highlights": ["CT OK", "1 proprio"],
  "concerns": ["km eleve pour l'annee"],
  "summary_fr": "iQ 2011 68k km, bon etat, CT OK."
}]

IMPORTANT: Return ONLY a JSON array. No other text."""


def _build_analyst_prompt(listings: list[RawListing]) -> str:
    """Build the user prompt with listing data."""
    listings_data = []
    for l in listings:
        listings_data.append({
            "id": l.id, "title": l.title, "price": l.price,
            "year": l.year, "mileage_km": l.mileage_km,
            "transmission": l.transmission, "city": l.city,
            "lat": l.lat, "lon": l.lon,
            "seller_type": l.seller_type, "description": l.description,
        })

    return f"""Score these {len(listings)} Toyota iQ listings using the scoring rubric.
Orly coordinates: 48.7262, 2.3652.

LISTINGS:
{json.dumps(listings_data, ensure_ascii=False, indent=2)}

Return a JSON array with one scored object per listing."""


def analyze_listings(
    listings: list[RawListing],
    client: LLMClient,
    top_n: int = 10,
) -> tuple[list[ScoredListing], list[ScoredListing]]:
    """Score listings via LLM, return (shortlist_pro, shortlist_part)."""
    if not listings:
        return [], []

    prompt = _build_analyst_prompt(listings)
    response = client.query(
        messages=[{"role": "user", "content": prompt}],
        model_preference="local",
        system=ANALYST_SYSTEM_PROMPT,
    )

    scored_data = extract_json_from_text(response.text)
    if not scored_data or not isinstance(scored_data, list):
        logger.error(f"Analyst returned invalid JSON: {response.text[:200]}")
        return [], []

    raw_lookup = {l.id: l for l in listings}

    scored_listings = []
    for item in scored_data:
        try:
            raw = raw_lookup.get(item["id"])
            if not raw:
                continue

            breakdown = ScoreBreakdown(**item["score_breakdown"])
            scored = ScoredListing(
                **raw.model_dump(),
                score=item["score"],
                score_breakdown=breakdown,
                excluded=item.get("excluded", False),
                exclusion_reason=item.get("exclusion_reason"),
                red_flags=item.get("red_flags", []),
                highlights=item.get("highlights", []),
                concerns=item.get("concerns", []),
                summary_fr=item.get("summary_fr", ""),
            )
            scored_listings.append(scored)
        except Exception as e:
            logger.warning(f"Failed to parse scored listing {item.get('id', '?')}: {e}")

    active = [s for s in scored_listings if not s.excluded]
    pro = sorted([s for s in active if s.seller_type == "pro"], key=lambda x: x.score, reverse=True)[:top_n]
    part = sorted([s for s in active if s.seller_type != "pro"], key=lambda x: x.score, reverse=True)[:top_n]

    return pro, part
