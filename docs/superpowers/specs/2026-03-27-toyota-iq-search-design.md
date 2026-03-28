# Toyota iQ Agentic Car Search — Design Spec v2

**Date:** 2026-03-27
**Owner:** Jerome Martin
**Status:** Approved

---

## 1. Purpose

Find the best Toyota iQ automatic deals on the French used car market. The iQ is rare (~60 total listings in France, far fewer in automatic). This tool scrapes 4 platforms (LeBonCoin, La Centrale, Le Parking, AutoScout24), scores listings against weighted criteria, presents two ranked shortlists (professional / private sellers) for human review via Telegram and terminal, then generates pricing analysis and negotiation messages for approved listings.

**Success criteria:** Jerome's friend gets a curated shortlist via Telegram with automatic alerts for new listings, approve/reject capability, and ready-to-send negotiation messages. Jerome gets a mirror channel for oversight.

**UI Language:** The entire Telegram interface (command names, responses, menus, alerts, negotiation messages) MUST be in French. Commands: `/chercher`, `/liste`, `/approuver`, `/rejeter`, `/details`, `/intervalle`, `/statut`. No English in any user-facing Telegram output.

---

## 2. Locked Search Criteria

| Criterion | Value |
|-----------|-------|
| Make/Model | Toyota iQ |
| Transmission | Automatic only (CVT / Multidrive) |
| Max budget | 5,000 EUR |
| Max mileage | 150,000 km |
| Min year | 2009 |
| Search zone | All France, ranked by distance from Orly (48.7262, 2.3652) |

---

## 3. Architecture

### 3.1 Core Principle

Single long-running process on WS-002. Telegram bot (polling), scheduler (APScheduler), and agentic pipeline all in one process. Pipeline runs in a background thread so the bot stays responsive. Terminal CLI remains available for dev/debug.

### 3.2 System Diagram

```
┌─────────────────────────────────────────────────────┐
│              SINGLE PROCESS (run.py)                 │
│                                                      │
│  ┌──────────────┐  ┌────────────┐  ┌─────────────┐ │
│  │ TELEGRAM BOT │  │ SCHEDULER  │  │  CLI (dev)   │ │
│  │ (polling)    │  │ (APSched)  │  │              │ │
│  └──────┬───────┘  └─────┬──────┘  └──────┬──────┘ │
│         │                │                 │        │
│         └────────────────┼─────────────────┘        │
│                          ▼                          │
│              ┌─────────────────────┐                │
│              │  SUPERVISOR AGENT   │                │
│              │  (Claude Sonnet     │                │
│              │   tool_use loop)    │                │
│              └──┬──────┬──────┬───┘                 │
│                 │      │      │                     │
│          ┌──────▼┐ ┌───▼───┐ ┌▼────────┐           │
│          │SCRAPER│ │ANALYST│ │ PRICER   │           │
│          │(4 src)│ │(Ollama)│ │(Sonnet) │           │
│          └───────┘ └───────┘ └─────────┘            │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │              NOTIFICATION LAYER               │   │
│  │  Friend chat: shortlists, alerts, approve/rej │   │
│  │  Jerome chat: mirror, errors, override        │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 3.3 Components

| Component | Type | Model | Purpose |
|-----------|------|-------|---------|
| Supervisor | LLM agent | Claude Sonnet | Mission controller. Decides what happens next. |
| Scraper LBC | Code | N/A | LeBonCoin scraper |
| Scraper LC | Code | N/A | La Centrale scraper |
| Scraper LP | Code | N/A | Le Parking scraper |
| Scraper AS24 | Code | N/A | AutoScout24 scraper |
| Analyst | LLM agent | Ollama Llama 3.1 8B (fallback: Claude Haiku) | Scores listings against rubric |
| Pricer | LLM agent | Claude Sonnet | Market pricing + negotiation messages |
| HITL Terminal | Terminal UI | N/A | Jerome dev/debug interface |
| Telegram Bot | Long-running | N/A | Friend primary interface + Jerome mirror |
| Scheduler | APScheduler | N/A | Configurable recurring runs (1h-1w) |

---

## 4. Data Flow

```
[LeBonCoin]───┐
[La Centrale]──┤                         ┌── shortlist_pro[]
[Le Parking]───┼── list[RawListing] ──→ ANALYST ──┤
[AutoScout24]──┘     (dedup)             │        └── shortlist_part[]
                                         │                │
                              SUPERVISOR                   │
                              (tool_use loop)              ▼
                                         │    HITL (Telegram + terminal)
                                         │                │
                                         │         approved_listings[]
                                         │                │
                                         └──────→ PRICER ─┘
                                                    │
                                             PricedListing[]
                                             + nego messages
                                                    │
                                              ┌─────▼──────┐
                                              │  TELEGRAM   │
                                              │  notify     │
                                              └────────────┘
```

### 4.1 Data Models (boundaries)

**RawListing** — output of scraper, input to analyst:
- id, platform, title, price, year, mileage_km, transmission, fuel
- city, department, lat, lon, seller_type, url, description, images
- scraped_at (ISO 8601)

**ScoredListing** — output of analyst:
- All RawListing fields + score (0-100), score_breakdown, excluded flag
- exclusion_reason, red_flags, highlights, concerns
- summary_fr (one-line French summary)

**PricedListing** — output of pricer:
- Reference to ScoredListing + market_estimate (low/high)
- opening_offer, max_acceptable, negotiation anchors
- message_digital (French, vouvoiement), message_oral_points

All models enforced via Pydantic v2. No raw dicts cross module boundaries.

---

## 5. Supervisor Agent

### 5.1 Mechanism

Claude Sonnet via Anthropic `tool_use` API. The supervisor runs in a loop:

1. Read current pipeline state
2. Reason about what to do next (in its response)
3. Call a tool
4. Evaluate the tool result
5. Update state
6. Loop back to 1

Exits when: human approves final output OR types "quit" / `/quit`.

### 5.2 Tools (8)

| Tool | Signature | Returns |
|------|-----------|---------|
| `scrape_platforms` | `(platforms: list[str])` | `{count, platforms_ok, platforms_failed}` |
| `get_raw_listings` | `()` | `list[RawListing]` summary |
| `dispatch_analyst` | `(top_n: int)` | `{shortlist_pro, shortlist_part}` |
| `dispatch_pricer` | `(listing_ids: list[str])` | `list[PricedListing]` |
| `ask_human` | `(question, context)` | Human's response (uses HITL interface when shortlists available) |
| `read_state` / `write_state` | `()` / `(updates)` | State JSON |
| `notify_telegram` | `(message, target)` | Send message to friend/jerome/both |

### 5.3 Decision Logic (in system prompt)

- No fresh data (<4 hours old)? Scrape.
- Scraped but not analyzed? Dispatch analyst.
- Analyst returned invalid output? Retry (max 2x), then escalate.
- Shortlists ready? Present to human via ask_human.
- Human approved listings? Dispatch pricer.
- 0 listings? Tell human, suggest retry later.
- 1+ platforms failed? Continue with partial data.
- Human says "rescrape"? Force fresh scrape.

---

## 6. Scrapers (4 platforms)

Pure code, not agents. All 4 run in parallel (threading).

### 6.1 LeBonCoin

**Fallback chain:** API endpoint -> `__NEXT_DATA__` JSON -> HTML parse.
Anti-detection: random delays 2-5s, User-Agent rotation, exponential backoff on 403/429.

### 6.2 La Centrale

**Approach:** `__NEXT_DATA__` JSON extraction -> HTML fallback.
Geocoding for city->GPS: hardcoded cache + Nominatim fallback.

### 6.3 Le Parking

**Approach:** HTML scraping (aggregator site). Le Parking aggregates from multiple sources. May overlap with LBC/LC listings — dedup handles this.

### 6.4 AutoScout24

**Approach:** API JSON (preferred) or HTML scraping. AutoScout24 has a structured search API.

### 6.5 Deduplication

Cross-platform dedup by normalized key: `(title_normalized, price, year, city_normalized)`.

### 6.6 Output

`list[RawListing]` saved to `_IQ/raw_listings_YYYYMMDD.json`.

---

## 7. Analyst Agent

### 7.1 Model

Primary: Ollama Llama 3.1 8B (local, free, fast).
Fallback: Claude Haiku (if Ollama unavailable or returns invalid output).

### 7.2 Scoring Rubric (100 points)

| Category | Max | Scale |
|----------|-----|-------|
| Price | 30 | 5000=0, 4000=15, 3000=25, <2500=30 |
| Mileage | 20 | 150k=0, 100k=10, 70k=15, <50k=20 |
| Year | 15 | 2009=5, 2011=10, 2013+=15 |
| Proximity to Orly | 15 | <20km=15, 20-30=8, 30-40=3, >40=0 |
| Condition signals | 10 | Capped at 10. Base=0. CT OK +5, carnet +5, 1 proprio +5, "en l'etat" -10, "accident" -10 |
| Transmission confirmed | 10 | Auto confirmed=10, unclear=0, manual=EXCLUDE |

### 7.3 Red Flags

- Manual transmission -> EXCLUDE (score = -1)
- Price > 5,000 EUR -> EXCLUDE
- Mileage > 150,000 km -> EXCLUDE
- "en l'etat" / "accidente" / "pour pieces" -> max 20 points total
- Fleet/commercial vehicle (SIV, GA, Uber) -> -10 points

### 7.4 Output

Two sorted lists:
- `shortlist_pro[]` — professional sellers, sorted by score descending
- `shortlist_part[]` — private sellers, sorted by score descending

---

## 8. HITL Interface

### 8.1 Telegram (primary for friend)

Friend commands:
- `/start` — welcome, explain bot
- `/search` — trigger immediate scrape + analysis
- `/shortlist` — re-send current shortlist
- `/approve 1,3,5` — approve listings by global number
- `/reject 2,4` — reject listings
- `/details 3` — full description
- `/interval 4h` — set scan frequency (1h to 1w)
- `/status` — current state

Jerome mirror: receives all shortlists + alerts + errors. Same commands available for override.

### 8.2 New listing alerts

When a scheduled run finds listings not previously seen (by listing ID), bot sends alert to friend + Jerome:
```
New listing found!
#1 [82/100] 2012 iQ 1.33 CVT — 52,000 km — 3,200 EUR
Vitry-sur-Seine (8 km) | Pro
+ CT OK, 1 proprio
https://www.leboncoin.fr/...

Reply /approve 1 or /reject 1
```

### 8.3 Terminal (dev/debug for Jerome)

Same display format as previous spec. Commands: ok, ok 1,3, drop, details, rescrape, top N, quit.

### 8.4 Global numbering

Pro listings numbered first (1-N), then particulier (N+1-M). Consistent across Telegram and terminal.

---

## 9. Pricer Agent

### 9.1 Model

Claude Sonnet. Quality matters for French negotiation prose.

### 9.2 Per Listing Output

- Market estimate: low/high range
- Opening offer, max acceptable
- Negotiation anchors (specific weak points)
- Digital message: French text (vouvoiement)
- Oral talking points

---

## 10. Scheduler

APScheduler with `IntervalTrigger`. Default: every 4 hours.

- Configurable via Telegram `/interval` command (1h to 1w)
- Interval stored in state file, survives restart
- Each run: scrape -> analyze -> diff previous -> alert new listings -> update state

---

## 11. LLM Client

Unified interface:
```
query(messages, model_preference, system) -> LLMResponse
query_with_tools(messages, tools, system, model) -> tool_use response
```

Fallback chains:
- "local": Ollama -> Claude Haiku -> Claude Sonnet
- "haiku": Claude Haiku -> Claude Sonnet
- "sonnet": Claude Sonnet (no fallback)

---

## 12. State Persistence

JSON file at `_IQ/state.json`. Tracks:
- Last scrape timestamp per platform
- Raw listing count, known listing IDs (for new listing detection)
- Analysis/pricing status
- Approved listing IDs
- Scheduler interval setting
- Current pipeline step

---

## 13. Distance Zones

From Orly (48.7262, 2.3652):

| Zone | Radius | Score Bonus |
|------|--------|-------------|
| PRIME | < 20 km | +15 pts |
| NEAR | 20-30 km | +8 pts |
| FAR | 30-40 km | +3 pts |
| REMOTE | > 40 km | 0 |

---

## 14. File Structure

```
G:\Downloads\_search_vehicles\
├── .env                        # API keys + Telegram tokens
├── .env.example
├── config.py                   # Criteria, constants, zones, bot config
├── models.py                   # Pydantic v2 models
├── utils.py                    # Haversine, geocoding, text, JSON extraction
├── llm_client.py               # Unified LLM (Ollama + Anthropic)
├── state.py                    # Pipeline state persistence
├── scraper_lbc.py              # LeBonCoin
├── scraper_lacentrale.py       # La Centrale
├── scraper_leparking.py        # Le Parking
├── scraper_autoscout.py        # AutoScout24
├── agent_analyst.py            # Analyst agent
├── agent_pricer.py             # Pricer agent
├── agent_supervisor.py         # Supervisor agent loop
├── hitl.py                     # Terminal HITL (dev/debug)
├── telegram_bot.py             # Telegram bot + handlers
├── scheduler.py                # APScheduler wrapper
├── run.py                      # Entry point (bot + scheduler + CLI)
├── requirements.txt
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   ├── test_models.py
│   ├── test_scraper_lbc.py
│   ├── test_scraper_lacentrale.py
│   ├── test_scraper_leparking.py
│   ├── test_scraper_autoscout.py
│   ├── test_analyst.py
│   ├── test_pricer.py
│   ├── test_supervisor.py
│   ├── test_telegram.py
│   └── test_scheduler.py
└── _IQ/                        # Output directory
```

---

## 15. Error Handling

| Failure | Response |
|---------|----------|
| Ollama unavailable | Fallback to Claude Haiku |
| Claude API error | Retry 2x, exponential backoff |
| Any scraper blocked | Continue with other platforms |
| LLM invalid JSON | Retry 2x with stricter prompt |
| 0 listings | Report to human, suggest retry later |
| Nominatim down | Use hardcoded city cache |
| Telegram API down | Log error, pipeline continues, results saved locally |

---

## 16. Security

- API keys + Telegram tokens in `.env`
- `.gitignore`: `.env`, `_IQ/*.json`, `__pycache__`
- Rate limiting per platform TOS

---

## 17. Dependencies

```
requests
beautifulsoup4
anthropic
pydantic>=2.0
python-dotenv
python-telegram-bot>=20.0
apscheduler>=3.10
pytest
```

---

## 18. Out of Scope

- L'Argus price reference (no accessible API)
- VPS deployment (stays on WS-002)
- Price history tracking
- Listing contact tracker
