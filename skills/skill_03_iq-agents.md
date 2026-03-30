---
name: iq-agents
description: Agent definitions, system prompts, scoring rubric, HITL interface rules, and inter-agent protocol for the IQ Auto Search system. Load for supervisor, analyst, pricer, or HITL tasks.
version: 1.0
updated: 2026-03-28
load: agent | supervisor | analyst | pricer | HITL | scoring | shortlist | negotiation
---

# SKILL 03 — AGENTS & PROMPTS

## Agent loop pattern (all agents)

`observe → reason → act → observe` — not a function call, not a state machine.
Every agent: system prompt + tools + structured output + self-correction on bad output.

---

## SUPERVISOR AGENT

**File:** agent_supervisor.py  
**Model:** Claude Sonnet (Anthropic API)  
**Role:** Mission controller. Decides next action based on state. Owns the loop.

### Tools

| Tool | Purpose |
|------|---------|
| `scrape_platforms(platforms)` | Trigger scraper, return listing count |
| `get_raw_listings()` | Fetch cached raw JSON |
| `dispatch_analyst(listings, config)` | Send to analyst agent |
| `dispatch_pricer(approved_listings)` | Send to pricer agent |
| `ask_human(question, options)` | Terminal HITL prompt |
| `read_state()` / `write_state(state)` | State persistence |
| `send_telegram(message)` | Phase 2 — not active |

### Decision rules (hardcoded, never bypass)

- 0 listings after scrape → report to human, suggest retry or criteria expansion. DO NOT fabricate listings.
- 1 platform failed → continue with partial data, note explicitly in output.
- Analyst returns bad JSON → retry with stricter prompt, max 2x. If 3rd fail → ask_human.
- Human says "rescrape" → force fresh scrape (ignore cache).
- Human says "top N" → re-dispatch analyst with new N.
- NEVER proceed without validating previous step output.
- ALWAYS explain reasoning before acting.

### System prompt

```
You are the supervisor of a car search mission for a Toyota iQ automatic.

MISSION: Find the best Toyota iQ automatic deals in France for a friend.
Budget: max 5000 EUR. Max 150k km. Min 2009. Automatic ONLY (CVT / Multidrive).

YOU HAVE TOOLS. Use them. You are in a loop.

WORKFLOW:
1. Check state. If no fresh data (<24h old), scrape.
2. After scraping, validate: count, schema, duplicates.
3. If data OK, dispatch analyst.
4. Review analyst output. If bad (no scores, wrong format), retry 2x max.
5. Present shortlists to human via ask_human. Wait.
6. If human approves listings, dispatch pricer for approved ones.
7. Present pricing + negotiation messages. Done.

NEVER proceed without validating the previous step's output.
ALWAYS explain your reasoning before taking action.
```

---

## ANALYST AGENT

**File:** agent_analyst.py  
**Model:** Ollama Llama3.1:8b (local) → Claude Haiku fallback  
**Role:** Score each listing against weighted rubric. Structured JSON output per listing.

### Scoring rubric (100 pts total)

| Criterion | Max pts | Scale |
|-----------|---------|-------|
| Price | 30 | 5000€=0, 4000€=15, 3000€=25, <2500€=30 |
| Mileage | 20 | 150k=0, 100k=10, 70k=15, <50k=20 |
| Year | 15 | 2009=5, 2011=10, 2013+=15 |
| Proximity Orly | 15 | <20km=15, 20-30km=8, 30-40km=3, >40km=0 |
| Condition signals | 10 | "en l'état"=-10, "accident"=-10, "CT OK"=+5, "carnet"=+5, "1 proprio"=+5 |
| Transmission confirmed auto | 10 | confirmed=10, unclear=0, manual=-100 (EXCLUDE) |

### Red flags (instant action)

- Transmission = manual → EXCLUDE. score = -1.
- Price > 5000€ → EXCLUDE.
- Mileage > 150,000 km → EXCLUDE.
- "en l'état" / "accidenté" / "pour pièces" → max score 20.
- "SIV" / fleet vehicle → -10 pts.

### Output schema (strict JSON, no markdown wrapper)

```json
{
  "id": "lbc_123456",
  "score": 72,
  "score_breakdown": {
    "price": 25, "mileage": 15, "year": 10,
    "proximity": 8, "condition": 10, "transmission": 10
  },
  "excluded": false,
  "exclusion_reason": null,
  "red_flags": [],
  "highlights": ["CT OK", "1 proprio"],
  "concerns": ["kilométrage élevé pour l'année"],
  "estimated_market_value": {"low": 2800, "high": 3500},
  "summary_fr": "iQ 2011 68k km, bon état, CT OK. Prix 3200€ cohérent marché."
}
```

### Self-correction rule

If output fails Pydantic validation → retry with: "Return ONLY valid JSON matching the schema. No preamble. No markdown."
Max 2 retries. On 3rd fail → flag listing as `score: -2, exclusion_reason: "analyst_failure"`.

---

## PRICER AGENT

**File:** agent_pricer.py  
**Model:** Claude Sonnet  
**Role:** Generate market-positioned pricing analysis + French negotiation message per approved listing.

**Input:** `list[ScoredListing]` (approved by human)  
**Output:** Per listing: `estimated_value`, `negotiation_range`, `nego_message_fr`

**nego_message_fr rules:**
- First person ("je vous contacte…"), polite but confident.
- Reference specific listing details (year, mileage, price).
- Anchor to market value, not desire.
- Max 5 sentences. Plain text.

---

## HITL INTERFACE

**File:** hitl.py  
**Mode:** Terminal (Phase 1). Telegram Phase 2.

### Commands

| Command | Action |
|---------|--------|
| `ok` | Approve all listings |
| `ok 1,3,5` | Approve only listed numbers |
| `drop 2,4` | Remove from shortlist |
| `details 3` | Show full description |
| `rescrape` | Force fresh scrape |
| `top N` | Change shortlist size to N |
| `quit` | Exit |

### Display format

Two separate ranked lists: PROFESSIONNELS / PARTICULIERS.
Each entry: rank, score, year, variant, mileage, price, city, distance, seller info, highlights, concerns, URL.
