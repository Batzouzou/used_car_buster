"""Pricer agent: market pricing + negotiation message generation via Claude Sonnet."""
import json
import logging
from models import ScoredListing, PricedListing
from llm_client import LLMClient
from utils import extract_json_from_text

logger = logging.getLogger(__name__)

PRICER_SYSTEM_PROMPT = """You are a French used car negotiation expert.

For each approved listing, produce:
1. Market price estimate (fourchette basse/haute) based on year, km, condition
2. Recommended opening offer (aggressive but not insulting)
3. Maximum acceptable price (walk-away point)
4. Negotiation anchors: specific weak points to leverage (km, age, condition, market rarity)
5. A ready-to-send message in French (vouvoiement, polite but informed)
   - For digital platforms (LBC message, email)
6. Oral talking points for phone/in-person

TONE: Informed buyer, respectful, not desperate. Reference specific facts about the car.
Never insult the seller or the car. Use "je me permets de vous proposer" style.

OUTPUT SCHEMA (strict JSON array, no markdown):
[{
  "id": "lbc_123456",
  "market_estimate_low": 2500,
  "market_estimate_high": 3200,
  "opening_offer": 2400,
  "max_acceptable": 3000,
  "anchors": ["Kilometrage superieur a la moyenne", "CT a refaire"],
  "message_digital": "Bonjour, je me permets de vous contacter...",
  "message_oral_points": ["Mentionner le kilometrage", "Demander le carnet"]
}]

IMPORTANT: Return ONLY a JSON array. No other text."""


def _build_pricer_prompt(listings: list[ScoredListing]) -> str:
    """Build the user prompt with listing data for pricing."""
    data = []
    for l in listings:
        data.append({
            "id": l.id, "title": l.title, "price": l.price,
            "year": l.year, "mileage_km": l.mileage_km,
            "city": l.city, "seller_type": l.seller_type,
            "score": l.score, "highlights": l.highlights,
            "concerns": l.concerns, "red_flags": l.red_flags,
            "description": l.description,
        })

    return f"""Price these {len(listings)} approved Toyota iQ listings and generate negotiation strategies.

LISTINGS:
{json.dumps(data, ensure_ascii=False, indent=2)}

Return a JSON array with pricing and negotiation data for each listing."""


def price_listings(
    listings: list[ScoredListing],
    client: LLMClient,
) -> list[PricedListing]:
    """Price approved listings via Claude Sonnet."""
    if not listings:
        return []

    prompt = _build_pricer_prompt(listings)
    response = client.query(
        messages=[{"role": "user", "content": prompt}],
        model_preference="sonnet",
        system=PRICER_SYSTEM_PROMPT,
    )

    priced_data = extract_json_from_text(response.text)
    if not priced_data or not isinstance(priced_data, list):
        logger.error(f"Pricer returned invalid JSON: {response.text[:200]}")
        return []

    scored_lookup = {l.id: l for l in listings}

    priced_listings = []
    for item in priced_data:
        try:
            scored = scored_lookup.get(item["id"])
            if not scored:
                continue

            priced = PricedListing(
                **scored.model_dump(),
                market_estimate_low=item["market_estimate_low"],
                market_estimate_high=item["market_estimate_high"],
                opening_offer=item["opening_offer"],
                max_acceptable=item["max_acceptable"],
                anchors=item.get("anchors", []),
                message_digital=item.get("message_digital", ""),
                message_oral_points=item.get("message_oral_points", []),
            )
            priced_listings.append(priced)
        except Exception as e:
            logger.warning(f"Failed to parse priced listing {item.get('id', '?')}: {e}")

    return priced_listings
