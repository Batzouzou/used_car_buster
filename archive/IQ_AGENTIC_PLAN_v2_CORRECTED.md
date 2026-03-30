# Toyota iQ Auto — Agentic Car Search System v2

## What Failed in v1 (Autopsy)

1. **Not agentic.** v1 was a linear ETL pipeline (`scrape → score → display → price`) with one-shot LLM calls. No reasoning loops, no self-correction, no tool-use agents.
2. **No supervisor agent.** The "orchestrator" was a dumb state machine with hardcoded transitions. No agent capable of reasoning about state, adjusting strategy, or recovering intelligently.
3. **Zero prompts.** Two modules depended on LLM calls with no prompt engineering — no system prompts, no schemas, no few-shot examples.
4. **Scoring rubric = ghost.** "Score 0-100" with no weights, no normalization, no breakdown.
5. **HITL undefined.** "VALIDER QUOI?" — no review interface, no decision criteria, no UX.
6. **Scraping = naive.** LeBonCoin actively blocks scrapers. No anti-detection strategy.
7. **No LLM fallback.** Ollama/local models mentioned in notes but never architected.
8. **No security.** API keys in config.py, no `.env`, no secrets management.

---

## Context

Jerome helps a friend find the best **Toyota iQ automatic** on the used car market. The iQ is rare in France (~60 total listings, far fewer in automatic). The friend has a Telegram bot (project POOL) for notifications.

The system must exhaustively search used car platforms, analyze listings against weighted criteria, produce two ranked shortlists (pro sellers / private sellers), then generate negotiation strategies per approved listing.

---

## Locked Search Criteria

| Criterion | Value |
|-----------|-------|
| Make/Model | Toyota iQ |
| Transmission | **Automatic only** (CVT / Multidrive) |
| Max budget | 5,000 EUR |
| Max mileage | 150,000 km |
| Min year | 2009 |
| Search zone | All France, ranked by distance from Orly |

---

## v2 Architecture: Actually Agentic

### Core Principle

An **agent** = a loop: `observe → reason → act → observe`. Not a function call. Each agent has tools, a system prompt, structured output, and the ability to self-correct through multiple iterations.

### System Diagram

```
┌─────────────────────────────────────────────────────┐
│                  SUPERVISOR AGENT                     │
│  (Claude Sonnet — reasoning + orchestration)          │
│                                                       │
│  Role: Owns the mission. Decides what to do next.     │
│  Tools: dispatch_scraper, dispatch_analyst,            │
│         dispatch_pricer, ask_human, read_state,        │
│         write_state, send_telegram                     │
│                                                       │
│  Loop:                                                │
│    1. Read current state (what data do I have?)       │
│    2. Decide next action (scrape? analyze? ask human?)│
│    3. Dispatch sub-agent or tool                      │
│    4. Evaluate result (good? retry? escalate?)        │
│    5. Update state → loop back to 1                   │
│                                                       │
│  Exits when: human approves final shortlist OR        │
│              human types "quit"                        │
└───────────┬──────────┬──────────┬─────────────────────┘
            │          │          │
     ┌──────▼──┐  ┌────▼────┐  ┌─▼────────┐
     │ SCRAPER │  │ ANALYST │  │  PRICER   │
     │ (code)  │  │ (agent) │  │  (agent)  │
     └─────────┘  └─────────┘  └──────────┘
```

### Agent Definitions

#### 1. SUPERVISOR AGENT (the brain)

**What v1 was missing entirely.**

- **Model:** Claude Sonnet (via Anthropic API)
- **Role:** Mission controller. Decides what happens next based on current state.
- **System prompt:** Defined below.
- **Tools available:**
  - `scrape_platforms(platforms: list)` → triggers scraper code, returns listing count
  - `get_raw_listings()` → returns cached raw data
  - `dispatch_analyst(listings: json, config: json)` → sends data to analyst agent
  - `dispatch_pricer(approved_listings: json)` → sends data to pricer agent
  - `ask_human(question: str, options: list)` → prompts Jerome in terminal
  - `read_state()` / `write_state(state: json)` → persistent state file
  - `send_telegram(message: str)` → notify friend's bot (Phase 2)

**Supervisor System Prompt:**
```
You are the supervisor of a car search mission for a Toyota iQ automatic.

YOUR MISSION: Find the best Toyota iQ automatic deals in France for a friend.
Budget: max 5000 EUR. Max 150k km. Min 2009. Automatic only.

YOU HAVE TOOLS. Use them. You are in a loop.

WORKFLOW:
1. Check state. If no fresh data (<24h), scrape.
2. After scraping, validate data quality (count, schema, duplicates).
3. If data looks good, dispatch analyst.
4. Review analyst output. If garbage (no scores, wrong format), retry up to 2x.
5. Present shortlists to human. Wait for decision.
6. If human approves listings, dispatch pricer for approved ones.
7. Present pricing + negotiation messages. Done.

DECISION RULES:
- 0 listings after scrape? Report to human, suggest expanding criteria or waiting.
- 1 platform failed? Continue with partial data, note it.
- Analyst returns bad JSON? Retry with stricter prompt, max 2x.
- Human says "rescrape"? Go back to step 1, force fresh scrape.
- Human says "top N"? Re-dispatch analyst with new N.

NEVER proceed without validating the previous step's output.
ALWAYS explain your reasoning before taking action.
```

#### 2. SCRAPER MODULE (deterministic code, not an agent)

**Not an agent** — this is pure code. Agents don't scrape; code does.

- `scraper_lbc.py` — LeBonCoin
- `scraper_lacentrale.py` — La Centrale
- Returns: `list[RawListing]` as JSON

**Anti-detection strategy:**
- Random delays: 2-5s between requests
- Realistic headers (User-Agent rotation from curated list)
- Session management (cookies, referer chains)
- Exponential backoff on 403/429
- Cache raw HTML for debug/replay
- **Fallback chain:** LBC API → LBC `__NEXT_DATA__` JSON → LBC HTML parse

**Output schema (enforced, not hoped for):**
```python
@dataclass
class RawListing:
    id: str                    # platform_id (e.g., "lbc_123456")
    platform: str              # "leboncoin" | "lacentrale"
    title: str
    price: int                 # EUR
    year: int
    mileage_km: int | None
    transmission: str | None   # "auto" | "manual" | "unknown"
    fuel: str | None
    city: str
    department: str | None
    lat: float | None
    lon: float | None
    seller_type: str           # "pro" | "private" | "unknown"
    url: str
    description: str | None
    images: list[str]
    scraped_at: str            # ISO 8601
    raw_html_path: str | None  # debug reference
```

#### 3. ANALYST AGENT (LLM-powered, with tools)

**This IS an agent** — it reasons over each listing, can request more info, and self-corrects.

- **Model:** Local LLM via Ollama (Llama 3.1 8B/70B depending on RAM) — cheap, high-volume scoring. Fallback: Claude Sonnet.
- **Why local:** Scoring 60 listings x detailed analysis = many tokens. Local = free. Quality is sufficient for structured scoring.

**System prompt:**
```
You are a used car analyst specializing in the French market.

TASK: Score each Toyota iQ listing against the buyer's criteria.
Output a JSON object per listing with the exact schema below.

SCORING RUBRIC (100 points total):
- Price (30 pts): 5000€=0, 4000€=15, 3000€=25, <2500€=30
- Mileage (20 pts): 150k=0, 100k=10, 70k=15, <50k=20
- Year (15 pts): 2009=5, 2011=10, 2013+=15
- Proximity to Orly (15 pts): <20km=15, 20-30km=8, 30-40km=3, >40km=0
- Condition signals (10 pts): "en l'état"=-10, "accident"=-10, "CT OK"=+5,
  "carnet entretien"=+5, "1 propriétaire"=+5
- Transmission confirmed auto (10 pts): confirmed=10, unclear=0, manual=-100 (EXCLUDE)

RED FLAGS (instant exclude or heavy penalty):
- Transmission = manual → EXCLUDE (score = -1)
- Price > 5000€ → EXCLUDE
- Mileage > 150000 km → EXCLUDE
- "en l'état" / "accidenté" / "pour pièces" → score = max 20
- "SIV" / fleet vehicle → -10 pts

OUTPUT SCHEMA (strict JSON, no markdown):
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
  "highlights": ["CT OK", "1 proprio", "carnet entretien"],
  "concerns": ["kilométrage élevé pour l'année"],
  "estimated_market_value": {"low": 2800, "high": 3500},
  "summary_fr": "iQ 2011 68k km, bon état, CT OK, 1 proprio. Prix demandé 3200€ cohérent."
}
```

**Tools available to analyst:**
- `get_listing_details(id)` → fetch full description if summary was truncated
- `check_argus_estimate(year, km, model)` → L'Argus cote (Phase 2, stub for now)

**Output:** Two sorted lists:
- `shortlist_pro[]` — top N professional sellers, sorted by score desc
- `shortlist_part[]` — top N private sellers, sorted by score desc

#### 4. PRICER + NEGOTIATOR AGENT (LLM-powered)

- **Model:** Claude Sonnet (needs quality for nuanced French negotiation language)
- **Why Sonnet:** Negotiation messages must be culturally appropriate, persuasive, and varied. Local LLMs aren't good enough for this.

**System prompt:**
```
You are a French used car negotiation expert.

For each approved listing, produce:
1. Market price estimate (fourchette basse/haute) based on year, km, condition
2. Recommended opening offer (aggressive but not insulting)
3. Maximum acceptable price (walk-away point)
4. Negotiation anchors: specific weak points to leverage (km, age, condition, market rarity)
5. A ready-to-send message in French (vouvoiement, polite but informed)
   - Variant A: for digital platforms (LBC message, email)
   - Variant B: for phone/in-person (talking points, not a script)

TONE: Informed buyer, respectful, not desperate. Reference specific facts about the car.
Never insult the seller or the car. Use "je me permets de vous proposer" style.

OUTPUT SCHEMA:
{
  "id": "lbc_123456",
  "market_estimate": {"low": 2500, "high": 3200},
  "opening_offer": 2400,
  "max_acceptable": 3000,
  "anchors": [
    "Kilométrage supérieur à la moyenne pour ce modèle (85k vs ~65k médiane)",
    "CT à refaire dans 3 mois — coût estimé 100-200€ si travaux"
  ],
  "message_digital": "Bonjour, ...",
  "message_oral_points": ["Mentionner le kilométrage...", "Demander le carnet..."]
}
```

---

## HITL Interface (What Jerome Actually Sees)

v1 had no UX. v2 defines it.

### Terminal Review Flow

```
══════════════════════════════════════════════════
  TOYOTA iQ AUTO — SHORTLIST REVIEW
  Scraped: 2026-03-26 14:30 | Sources: LBC(42), LC(18)
  After filtering: 12 auto | Excluded: 48 (manual/over budget/etc)
══════════════════════════════════════════════════

── PROFESSIONNELS (6 résultats) ──────────────────

 #1 [87/100] 2012 iQ 1.33 Multidrive — 52,000 km — 3,200€
    📍 Vitry-sur-Seine (8 km) | Pro: Garage Central Auto
    ✓ CT OK, carnet, 2 proprios | ⚠ RAS
    🔗 https://www.leboncoin.fr/...

 #2 [74/100] 2011 iQ 1.33 CVT — 78,000 km — 2,800€
    📍 Créteil (12 km) | Pro: AutoPlus94
    ✓ 1 proprio | ⚠ CT à refaire
    🔗 https://www.lacentrale.fr/...

 ...

── PARTICULIERS (4 résultats) ───────────────────

 #1 [81/100] 2013 iQ 1.33 Multidrive — 45,000 km — 3,800€
    📍 Paris 15e (14 km) | Particulier
    ✓ CT OK, 1 proprio, faible km | ⚠ Prix un peu haut
    🔗 https://www.leboncoin.fr/...

 ...

══════════════════════════════════════════════════
COMMANDES:
  ok          → Approuver tout, passer au pricing
  ok 1,3,5    → Approuver seulement ces numéros
  drop 2,4    → Retirer ces numéros
  details 3   → Afficher description complète
  rescrape    → Relancer le scraping
  top N       → Changer la taille des listes
  quit        → Sortir
══════════════════════════════════════════════════
> _
```

---

## LLM Strategy: Local + Cloud Hybrid

| Agent | Model | Why | Fallback |
|-------|-------|-----|----------|
| Supervisor | Claude Sonnet (API) | Needs reasoning, tool-use, orchestration | — |
| Analyst | Ollama Llama 3.1 8B (local) | High volume, structured scoring, FREE | Claude Haiku |
| Pricer | Claude Sonnet (API) | Nuanced French, negotiation quality | Claude Haiku |

**WS-002 config:** Currently 32GB RAM → 64GB soon. Llama 3.1 8B runs comfortably in 8GB VRAM or ~10GB RAM (Q4_K_M quant). With 64GB you could run 70B (Q4 ≈ 40GB RAM) for better analyst quality.

**Ollama integration:**
```python
import requests

def query_local_llm(prompt: str, model: str = "llama3.1:8b") -> str:
    """Query Ollama local LLM with automatic fallback to Claude."""
    try:
        resp = requests.post("http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120)
        resp.raise_for_status()
        return resp.json()["response"]
    except Exception as e:
        logger.warning(f"Local LLM failed: {e}, falling back to Claude Haiku")
        return query_claude(prompt, model="claude-haiku-4-5-20251001")
```

---

## Geocoding

**Problem:** La Centrale gives city names, not GPS coordinates.

**Solution (unchanged, it was fine):**
- Hardcoded cache: top 30 IDF cities + major FR cities
- Fallback: Nominatim (free, OSM-based)
- Rate limit: 1 req/sec (Nominatim TOS)
- Cache all lookups to `geocode_cache.json`

**Distance zones from Orly (48.7262, 2.3652):**

| Zone | Radius | Score bonus |
|------|--------|-------------|
| PRIME | < 20 km | +15 pts |
| NEAR | 20-30 km | +8 pts |
| FAR | 30-40 km | +3 pts |
| REMOTE | > 40 km | 0 |

---

## File Structure

```
G:\Downloads\_search_vehicles\
├── .env                        # API keys (ANTHROPIC_API_KEY, etc.)
├── .env.example                # Template, no secrets
├── config.py                   # Criteria, constants, distance zones
├── models.py                   # Pydantic models (RawListing, ScoredListing, PricedListing)
├── utils.py                    # Haversine, geocoding, text cleanup
├── scraper_lbc.py              # LeBonCoin scraper
├── scraper_lacentrale.py       # La Centrale scraper
├── agent_supervisor.py         # SUPERVISOR agent loop
├── agent_analyst.py            # ANALYST agent (local LLM)
├── agent_pricer.py             # PRICER agent (Claude Sonnet)
├── hitl.py                     # Terminal HITL interface
├── llm_client.py               # Unified LLM client (Ollama + Anthropic, auto-fallback)
├── state.py                    # State persistence (JSON file)
├── run.py                      # CLI entry point
├── tests/
│   ├── conftest.py
│   ├── fixtures/               # Captured HTML/JSON for replay
│   ├── test_scraper.py
│   ├── test_analyst.py
│   ├── test_pricer.py
│   └── test_supervisor.py
└── _IQ/                        # Output directory
    ├── state.json              # Pipeline state
    ├── geocode_cache.json
    ├── raw_listings_YYYYMMDD.json
    ├── shortlist_pro_YYYYMMDD.json
    ├── shortlist_part_YYYYMMDD.json
    ├── shortlist_approved_YYYYMMDD.json
    ├── priced_YYYYMMDD.json
    └── nego_messages_YYYYMMDD.json
```

---

## Security & Best Practices

- **Secrets:** `.env` file, loaded via `python-dotenv`. Never in code.
- **`.gitignore`:** `.env`, `_IQ/*.json`, `__pycache__`, `*.pyc`
- **Rate limiting:** Respect platform TOS. Random delays, no parallel bombardment.
- **Pydantic validation:** All data flows through typed models. No raw dicts.
- **Logging:** `structlog` for structured JSON logs. Levels: DEBUG (dev), INFO (prod).
- **Error handling:** Every external call (HTTP, LLM) wrapped in try/except with retry logic.

---

## Dependencies

```
requests
beautifulsoup4
anthropic
pydantic
python-dotenv
structlog
```

Optional (local LLM):
```
# Ollama installed separately: https://ollama.ai
# Models: ollama pull llama3.1:8b
```

---

## CLI

```bash
python run.py                # Full pipeline (supervisor takes over)
python run.py scrape         # Scrape only, save raw data
python run.py analyze        # Analyze latest raw data
python run.py price          # Price latest approved shortlist
python run.py status         # Show current state
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LBC blocks scraping | No LBC data | Fallback chain: API → __NEXT_DATA__ → HTML. Anti-detection. Cache. |
| La Centrale HTML changes | Parser breaks | Fixtures + tests. Selector versioning. |
| 0 iQ auto listings | Empty pipeline | Expected for rare model. Supervisor reports to human, suggests retry later. |
| Local LLM quality too low | Bad scoring | Auto-fallback to Claude Haiku. Score validation (schema check). |
| Claude returns bad JSON | Analysis fails | Pydantic validation. Retry 2x with stricter prompt. Fallback to regex extraction. |
| Nominatim down | No geocoding for LC | Local cache covers 80% IDF cities. |
| API key leaked | Security breach | `.env` + `.gitignore`. Never log keys. |

---

## Phase 2 (Deferred, Defined)

| Feature | Priority | Dependency |
|---------|----------|------------|
| Telegram alerts (new listings) | HIGH | Friend's POOL bot |
| AutoScout24 scraper | MEDIUM | Same architecture |
| L'Argus price reference | MEDIUM | API or scrape |
| Le Parking aggregator | LOW | Redundant with LBC+LC |
| Scheduled daily runs (VPS) | MEDIUM | Stable Phase 1 |
| Listing tracker (already contacted) | HIGH | State file extension |
| Price history tracking | LOW | State file extension |

---

## What Makes This v2 Actually Agentic

1. **Supervisor agent with a reasoning loop** — not a state machine. It decides what to do based on context, not hardcoded transitions.
2. **Agents have tools** — analyst can request more details, pricer can look up references.
3. **Self-correction** — bad output triggers retry with adjusted prompts, not just "FAILED".
4. **Human in the loop with actual UX** — Jerome sees formatted shortlists with commands, not raw JSON.
5. **LLM fallback chain** — local → cloud haiku → cloud sonnet. Cost-optimized.
6. **Typed data flow** — Pydantic models enforce schemas at every boundary.
7. **Prompts are defined** — system prompts, scoring rubrics, output schemas. Not vibes.

