# Toyota iQ Auto — Agentic Car Search System v3

**Amends:** v2 CORRECTED → v3
**Date:** 2026-03-29
**Reason:** Code review findings, LM Studio migration, monitor UI, accuracy corrections

---

## Changelog v2 → v3

| # | Category | Change |
|---|----------|--------|
| A1 | MISMATCH | Scraping is **sequential** (for loop), not parallel. Documented accurately. |
| A2 | MISMATCH | Sonnet model ID confirmed: `claude-sonnet-4-20250514`. Haiku: `claude-haiku-4-5-20251001`. |
| A3 | CRITICAL FIX | LBC scraper: `GET` → `POST` with `json=` body. Added `api_key`, `Origin`, `Referer` headers. |
| A4 | CRITICAL FIX | CLI `price` command: glob pattern `shortlist_approved_*` → `approved_*` (aligned with supervisor output). |
| A5 | BUG FIX | Telegram `/statut`: step_fr keys aligned with supervisor values (`scraped`, `analyzed`, `priced`). |
| A6 | BUG FIX | CLI `scrape` command: added cross-platform dedup (same logic as supervisor). |
| A7 | MIGRATION | Local LLM: **Ollama → LM Studio** on `localhost:1234`, model `qwen3-vl-8b`. |
| A8 | NEW | Monitor HTML interface: Flask endpoint for pipeline status + shortlist viewer. |
| A9 | MINOR | Pagination stubs for La Centrale + AutoScout24 (noted, not blocking). |
| A10 | MINOR | La Centrale: single static UA → rotate from pool (align with other scrapers). |
| A11 | MINOR | `ScoreBreakdown.transmission`: field bound `ge=-100` narrowed to `ge=-1`. |
| A12 | MINOR | Supervisor `_tool_notify_telegram`: reuse event loop instead of creating new one per call. |
| A13 | MINOR | `extract_json_from_text`: document bracket-in-string limitation, add markdown fence stripping. |

---

## What Failed in v1 (Autopsy)

*Unchanged from v2 — see IQ_AGENTIC_PLAN_v2_CORRECTED.md*

---

## Context

Jerome helps a friend find the best **Toyota iQ automatic** on the used car market. The iQ is rare in France (~60 total listings, far fewer in automatic).

The system exhaustively searches 4 used car platforms, scores listings against a weighted 100-point rubric, produces two ranked shortlists (pro / private), then generates French negotiation strategies per approved listing.

**Interfaces:** Telegram bot (friend primary, Jerome mirror) + terminal HITL + **monitor web UI (new in v3)**.

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
| Distance ref | Orly airport (48.7262, 2.3652) |

---

## v3 Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    SUPERVISOR AGENT                       │
│  (Claude Sonnet claude-sonnet-4-20250514)                │
│  tool_use loop, max 20 iterations                        │
│                                                          │
│  Tools (8):                                              │
│    scrape_platforms, get_raw_listings, dispatch_analyst,  │
│    dispatch_pricer, ask_human, read_state, write_state,  │
│    notify_telegram                                       │
└──────┬──────────┬──────────┬──────────┬─────────────────┘
       │          │          │          │
  ┌────▼────┐ ┌───▼───┐ ┌───▼───┐ ┌───▼──────┐
  │SCRAPERS │ │ANALYST│ │PRICER │ │TELEGRAM  │
  │ (code)  │ │(agent)│ │(agent)│ │(bot+notif│
  │ 4 sites │ │LM Stu │ │Sonnet │ │  FR UI)  │
  └─────────┘ └───────┘ └───────┘ └──────────┘
                                        │
                                   ┌────▼────┐
                                   │MONITOR  │
                                   │(Flask)  │
                                   │ :5050   │
                                   └─────────┘
```

### Key Architecture Facts (Verified Against Code)

1. **Scraping is sequential**, not parallel. The supervisor's `_tool_scrape` iterates platforms in a `for` loop with 2-5s random delays per scraper. This is intentional — parallel requests from same IP increase detection risk.
2. **4 scrapers implemented:** LeBonCoin (API+POST), La Centrale (__NEXT_DATA__), Le Parking (HTML), AutoScout24 (__NEXT_DATA__).
3. **Single long-running process:** `run.py` starts Telegram bot (blocking main thread) + APScheduler (background thread) + pipeline via supervisor.
4. **PID lockfile** (`_IQ/bot.pid`) prevents 409 Conflict from multiple Telegram polling instances.

---

## Agent Definitions

### 1. SUPERVISOR AGENT

- **Model:** `claude-sonnet-4-20250514` (via Anthropic tool_use API)
- **Max iterations:** 20
- **Tools:** 8 (scrape_platforms, get_raw_listings, dispatch_analyst, dispatch_pricer, ask_human, read_state, write_state, notify_telegram)

**System Prompt:** *(unchanged from v2 — see agent_supervisor.py:17-42)*

### 2. SCRAPER MODULE (deterministic code)

4 scrapers, run **sequentially** (not parallel — A1):

| Scraper | Method | Anti-detection |
|---------|--------|----------------|
| `scraper_lbc.py` | **POST** to API (A3) with `api_key`, `Origin`, `Referer` headers | 3 rotating UAs, 2-5s delays, 403→fallback stub |
| `scraper_lacentrale.py` | GET HTML → `__NEXT_DATA__` JSON | **Single static UA (A10: should rotate)**, 2-5s delay |
| `scraper_leparking.py` | GET HTML → BeautifulSoup `.vehicle-card` | 3 rotating UAs, 2-5s delay, geocode via Nominatim |
| `scraper_autoscout.py` | GET HTML → `__NEXT_DATA__` JSON | 3 rotating UAs, 2-5s delay |

**Pagination status (A9):**
- LBC: implemented (offset-based loop)
- La Centrale: first page only (low volume OK for iQ)
- Le Parking: first page only
- AutoScout24: first page only

**Cross-platform dedup:** `(title_lower, price, year, city_lower)` — applied in both supervisor and CLI scrape (A6).

### 3. ANALYST AGENT

- **Model:** LM Studio `qwen3-vl-8b` on `localhost:1234` (A7) → Claude Haiku fallback → Claude Sonnet fallback
- **Endpoint:** OpenAI-compatible `/v1/chat/completions`
- **Scoring rubric:** 100 points (price 30, mileage 20, year 15, proximity 15, condition 10, transmission 10)
- **Output:** Two sorted lists: `shortlist_pro[]` + `shortlist_part[]`

**Why Qwen3-VL-8B:** Vision-language model can potentially analyze listing photos (Phase 2). For now, text-only scoring. Runs on RTX 4080 Super via LM Studio.

### 4. PRICER AGENT

- **Model:** `claude-sonnet-4-20250514` (direct, no fallback)
- **Output:** `PricedListing[]` with market estimates, opening offers, anchors, French nego messages (vouvoiement)

---

## LLM Strategy: LM Studio + Cloud Hybrid (A7)

### Migration: Ollama → LM Studio

| Aspect | Ollama (v2) | LM Studio (v3) |
|--------|-------------|-----------------|
| Port | `localhost:11434` | `localhost:1234` |
| API | `/api/chat` (Ollama native) | `/v1/chat/completions` (OpenAI-compatible) |
| Model | `llama3.1:8b` | `qwen3-vl-8b` |
| Config var | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | `LM_STUDIO_BASE_URL`, `LM_STUDIO_MODEL` |

**Changes required in code:**

1. **`config.py`** — Replace Ollama env vars:
   ```python
   # OLD
   OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
   OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

   # NEW
   LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234")
   LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "qwen3-vl-8b")
   ```

2. **`llm_client.py`** — Replace `_query_ollama` with `_query_lm_studio`:
   ```python
   # OLD: Ollama native API
   resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat",
       json={"model": OLLAMA_MODEL, "messages": msgs, "stream": False})
   return resp.json()["message"]["content"]

   # NEW: OpenAI-compatible API
   resp = requests.post(f"{LM_STUDIO_BASE_URL}/v1/chat/completions",
       json={"model": LM_STUDIO_MODEL, "messages": msgs, "stream": False,
             "temperature": 0.1, "max_tokens": 4096})
   return resp.json()["choices"][0]["message"]["content"]
   ```

3. **`llm_client.py` FALLBACK_CHAINS** — Rename key:
   ```python
   FALLBACK_CHAINS = {
       "local": ["lm_studio", "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
       "haiku": ["claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
       "sonnet": ["claude-sonnet-4-20250514"],
   }
   ```

4. **`.env`** — Update:
   ```
   LM_STUDIO_BASE_URL=http://localhost:1234
   LM_STUDIO_MODEL=qwen3-vl-8b
   ```

5. **Tests** — Update all mocks from `_query_ollama` to `_query_lm_studio`, update response parsing.

### Model Summary

| Agent | Model | Endpoint | Fallback |
|-------|-------|----------|----------|
| Supervisor | `claude-sonnet-4-20250514` | Anthropic API (tool_use) | — |
| Analyst | `qwen3-vl-8b` (LM Studio local) | `localhost:1234/v1/chat/completions` | Haiku → Sonnet |
| Pricer | `claude-sonnet-4-20250514` | Anthropic API | — |

---

## Monitor HTML Interface (A8) — NEW

### Purpose

Web-based read-only dashboard showing pipeline status, latest shortlists, and scrape history. Accessible at `http://localhost:5050`. For Jerome's local monitoring — no auth needed (local only).

### Endpoints

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Dashboard: pipeline state, last scrape time, listing counts |
| `/shortlist` | GET | Current shortlist (pro + private) with scores, formatted |
| `/raw` | GET | Latest raw listings table (sortable) |
| `/priced` | GET | Latest priced listings with nego messages |
| `/api/state` | GET | JSON: current `PipelineState` |
| `/api/listings` | GET | JSON: latest raw listings |

### Implementation

- **File:** `monitor.py` (~100-150 lines)
- **Stack:** Flask (already in requirements for future use), Jinja2 templates or inline HTML
- **Port:** 5050 (configurable via `MONITOR_PORT` env var)
- **Launch:** Started alongside bot in `run.py` (background thread, non-blocking)
- **No CSS framework** — minimal inline styles, monospace font, dark theme
- **Auto-refresh:** meta refresh every 60s on dashboard

### Template Structure

```
monitor.py
├── / (dashboard)
│   ├── Pipeline step: {state.step}
│   ├── Last scrape: {state.last_scrape_at}
│   ├── Raw listings: {state.raw_listing_count}
│   ├── Shortlist: {pro_count} pro / {part_count} private
│   └── Pricing: {state.pricing_status}
│
├── /shortlist
│   ├── PROFESSIONNELS table (score, year, title, price, km, city, distance)
│   └── PARTICULIERS table (same columns)
│
├── /raw
│   └── All raw listings table (id, platform, title, price, year, km, city, url)
│
└── /priced
    └── Priced listings with market_estimate, opening_offer, message preview
```

---

## Data Models (Pydantic v2 — Verified)

```
RawListing (17 fields) → ScoredListing (+8 fields) → PricedListing (+7 fields)
```

All cross-module boundaries use typed Pydantic models. No raw dicts.

**A11 fix:** `ScoreBreakdown.transmission` field bound narrowed from `ge=-100` to `ge=-1` (only -1 = excluded).

---

## File Structure (Actual, Verified)

```
G:\Downloads\_search_vehicles\
├── .env                        # API keys, LM Studio config, Telegram tokens
├── .env.example                # Template
├── .gitignore
├── requirements.txt
├── CLAUDE.md                   # Claude Code project instructions
├── PROJECT_DOC.md              # v4.3 documentation
├── IQ_AGENTIC_PLAN_v3.md       # This file
├── run.py                      # Entry point + PID lockfile + scheduler + bot
├── config.py                   # Criteria, constants, LM Studio config
├── models.py                   # Pydantic v2: RawListing, ScoredListing, PricedListing
├── utils.py                    # Haversine, geocoding, text cleanup, JSON extraction
├── state.py                    # PipelineState persistence (JSON)
├── llm_client.py               # Unified LLM client: LM Studio → Haiku → Sonnet
├── scraper_lbc.py              # LeBonCoin scraper (POST API + fallback)
├── scraper_lacentrale.py       # La Centrale scraper (__NEXT_DATA__) + geocoding
├── scraper_leparking.py        # Le Parking scraper (HTML)
├── scraper_autoscout.py        # AutoScout24 scraper (__NEXT_DATA__)
├── agent_supervisor.py         # Supervisor agent (Claude Sonnet tool_use loop)
├── agent_analyst.py            # Analyst agent (LM Studio scoring)
├── agent_pricer.py             # Pricer agent (Claude Sonnet nego)
├── hitl.py                     # Terminal HITL interface
├── telegram_bot.py             # Telegram bot (FR UI, 8 commands)
├── scheduler.py                # APScheduler wrapper
├── monitor.py                  # NEW: Flask monitor dashboard (:5050)
├── tests/                      # 17 test files, 263+ tests
│   ├── fixtures/               # Sample HTML/JSON for replay
│   └── ...
└── _IQ/                        # Output directory
    ├── state.json
    ├── bot.pid                 # PID lockfile
    ├── geocode_cache.json
    ├── raw_listings_YYYYMMDD.json
    ├── approved_YYYYMMDD.json  # Fixed filename (A4)
    └── priced_YYYYMMDD.json
```

---

## Output Files (Corrected — A4)

| File | Written by | Content |
|------|-----------|---------|
| `raw_listings_YYYYMMDD.json` | supervisor `_tool_scrape` or CLI `scrape` | All scraped + deduped listings |
| `approved_YYYYMMDD.json` | supervisor `_tool_pricer` | Approved shortlist before pricing |
| `priced_YYYYMMDD.json` | supervisor `_tool_pricer` | Priced listings with nego messages |
| `state.json` | supervisor (after every tool call) | Pipeline state |
| `bot.pid` | `run.py` on startup | Current process PID |
| `geocode_cache.json` | `scraper_lacentrale.py` | City → GPS cache |

---

## Telegram Bot (FR UI — Verified)

| Commande | Description |
|----------|-------------|
| `/start` | Afficher les commandes disponibles |
| `/chercher` | Lancer une recherche immediate |
| `/liste` | Voir la shortlist actuelle |
| `/approuver 1,3,5` | Approuver des annonces par numero |
| `/rejeter 2,4` | Rejeter des annonces par numero |
| `/details 3` | Details complets de l'annonce #3 |
| `/intervalle 4h` | Changer la frequence (min 1h, max 1s) |
| `/statut` | Etat du pipeline |

Step translations (A5 fix): `init→initial`, `scraped→scrape termine`, `analyzed→analyse terminee`, `priced→pricing termine`, `done→termine`.

---

## Minor Issues — Status & Plan

### A9: Pagination (La Centrale, AutoScout24)

**Status:** First page only. **Decision:** Not blocking. Toyota iQ automatic has ~60 total listings in France — first page covers all results on most platforms. Add pagination if volume increases or search criteria broaden.

### A10: La Centrale single UA

**Plan:** Add UA rotation pool (same 3 UAs as other scrapers) to `scraper_lacentrale.py` session setup. ~2 line change.

### A11: ScoreBreakdown.transmission field bounds

**Plan:** Change `Field(ge=-100, le=10)` to `Field(ge=-1, le=10)` in `models.py`. Score -1 = excluded, 0 = unclear, 10 = confirmed auto. No value below -1 is meaningful.

### A12: Event loop per Telegram notification

**Plan:** In `_tool_notify_telegram`, check for existing event loop before creating new one. Use `asyncio.get_event_loop()` with fallback to `asyncio.new_event_loop()`. Cache `TelegramNotifier` instance on the agent.

### A13: JSON extraction bracket limitation

**Status:** `extract_json_from_text` uses depth-tracking bracket matching which doesn't handle `{`/`}` inside JSON string values. **Plan:** Add markdown fence stripping (` ```json ... ``` `) before bracket matching. Document the limitation. For LLM-generated car listing JSON, this is extremely unlikely to cause issues.

---

## Implementation Order (Sprint 2)

| Step | Task | Files | Est. |
|------|------|-------|------|
| 1 | LM Studio migration (A7) | `config.py`, `llm_client.py`, `.env`, tests | Medium |
| 2 | Monitor Flask UI (A8) | `monitor.py` (new), `run.py` | Medium |
| 3 | Minor fixes (A10-A13) | `scraper_lacentrale.py`, `models.py`, `agent_supervisor.py`, `utils.py` | Small |
| 4 | Test suite update | `tests/test_llm_client.py`, new `tests/test_monitor.py` | Medium |
| 5 | First live run | All scrapers against real sites | Manual |

**Already done (this session):** A3, A4, A5, A6 — 3 critical + 2 bug fixes, 263 tests green.

---

## Risks & Mitigations (Updated)

| Risk | Impact | Mitigation |
|------|--------|------------|
| LBC blocks scraping | No LBC data | POST API with headers (A3), fallback stub ready |
| La Centrale HTML changes | Parser breaks | Fixtures + tests, selector versioning |
| 0 iQ auto listings | Empty pipeline | Expected for rare model. Supervisor reports to human. |
| LM Studio not running | Analyst fails | Fallback chain: LM Studio → Haiku → Sonnet (automatic) |
| Qwen3-VL-8B quality too low | Bad scoring | Schema validation + auto-fallback to Haiku |
| Claude returns bad JSON | Analysis fails | Pydantic validation, retry 2x, regex extraction fallback |
| Multiple bot instances | 409 Conflict | PID lockfile with SIGTERM→SIGKILL (implemented) |
| Monitor port conflict | UI unavailable | Configurable `MONITOR_PORT`, graceful fallback |

---

## Phase 2 (Deferred — Updated)

| Feature | Priority | Status |
|---------|----------|--------|
| ~~Telegram bot~~ | ~~HIGH~~ | **DONE** (telegram_bot.py) |
| ~~AutoScout24 scraper~~ | ~~MEDIUM~~ | **DONE** (scraper_autoscout.py) |
| ~~Le Parking scraper~~ | ~~LOW~~ | **DONE** (scraper_leparking.py) |
| ~~APScheduler~~ | ~~MEDIUM~~ | **DONE** (scheduler.py) |
| Qwen3-VL image analysis | MEDIUM | Model supports it, needs integration |
| L'Argus price reference | MEDIUM | API or scrape |
| Listing tracker (contacted) | HIGH | State file extension |
| Price history tracking | LOW | State file extension |
| VPS deployment | LOW | Stable local first |
