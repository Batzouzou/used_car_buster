---
name: iq-system
description: Core system context for Toyota iQ Auto Search v2. Load ALWAYS. Covers mission, architecture, agents, file structure, and operational constraints.
version: 1.0
updated: 2026-03-28
load: always
---

# SKILL 01 — SYSTEM CONTEXT

## Mission

Find the best Toyota iQ **automatic** (CVT / Multidrive) on the French used car market for a friend.
Exhaustive search → weighted scoring → ranked shortlists → negotiation strategies.

## Locked criteria

| Criterion | Value |
|-----------|-------|
| Make/Model | Toyota iQ |
| Transmission | Automatic ONLY (CVT / Multidrive S) |
| Max budget | 5,000 EUR |
| Max mileage | 150,000 km |
| Min year | 2009 |
| Search zone | All France, ranked by distance from Orly |
| Distance ref | Orly airport (48.7262, 2.3652) |

## Architecture

```
SUPERVISOR (Claude Sonnet) — reasoning loop, orchestration
    ├── SCRAPER MODULE (code, not agent) — LBC + La Centrale
    ├── ANALYST AGENT (Ollama Llama3.1:8b → Claude Haiku fallback)
    └── PRICER AGENT (Claude Sonnet) — negotiation strategies
```

## File structure

```
G:\Downloads\_search_vehicles\
├── .env                    # ANTHROPIC_API_KEY — never in code
├── config.py               # Criteria, distance zones, constants
├── models.py               # Pydantic: RawListing, ScoredListing, PricedListing
├── utils.py                # Haversine, geocoding, text cleanup
├── scraper_lbc.py          # LeBonCoin scraper
├── scraper_lacentrale.py   # La Centrale scraper
├── agent_supervisor.py     # Supervisor loop (observe→reason→act)
├── agent_analyst.py        # Analyst agent (scoring)
├── agent_pricer.py         # Pricer agent (negotiation)
├── hitl.py                 # Terminal HITL interface
├── llm_client.py           # Unified LLM client (Ollama + Anthropic)
├── state.py                # State persistence (JSON)
├── run.py                  # CLI entry point
├── tests/                  # pytest suite
└── _IQ/                    # Output: state.json, shortlists, priced, nego
```

## CLI

```bash
python run.py               # Full pipeline
python run.py scrape        # Scrape only
python run.py analyze       # Analyze latest raw data
python run.py price         # Price approved shortlist
python run.py status        # Show state
```

## Phase 2 (deferred)

Telegram alerts (POOL bot), AutoScout24 scraper, L'Argus price ref, scheduled VPS runs, listing tracker, price history.

## Known risks

- LBC blocks scrapers aggressively → anti-detection mandatory (see skill_02)
- ~60 total iQ listings in France, far fewer in automatic → low volume expected
- La Centrale: city names only, no GPS → Nominatim geocoding required
- Local LLM quality borderline for scoring → schema validation + auto-fallback
