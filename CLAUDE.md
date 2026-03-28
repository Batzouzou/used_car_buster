# CLAUDE.md — Toyota iQ Agentic Car Search System

## PROJET SÉPARÉ
**Ce projet n'a RIEN à voir avec My Gateway Premium (MGP).**
- Ne JAMAIS mélanger les deux projets
- Ne JAMAIS importer de config/mémoire MGP ici
- Ne JAMAIS référencer les memory files MGP dans ce contexte

## Ce que c'est
Outil agentic pour Jerome (et son ami via Telegram) pour trouver une Toyota iQ boîte automatique d'occasion en France.
Single long-running process (WS-002) : Telegram bot + APScheduler + Supervisor Agent (Claude Sonnet tool_use loop).
Pipeline: scrape 4 plateformes → analyse LLM → HITL (Telegram + terminal) → pricing + négo.

## Project Status (2026-03-28)
- **Fully implemented:** 16 source files (~2,200 lines), 17 test files (~2,800 lines)
- **263 tests passing** (all green, ~65s)
- **Never run live** — all tested with mocks, no real scraping/LLM calls yet
- **SESSION_RESTART.md** in memory/ has full context brief for new sessions

## Dossiers
- **Code source :** `G:\Downloads\_search_vehicles\`
- **Données de sortie :** `G:\Downloads\_search_vehicles\_IQ\`
- **Design spec :** `docs/superpowers/specs/2026-03-27-toyota-iq-search-design.md`
- **Implementation plan :** `docs/superpowers/plans/2026-03-27-toyota-iq-search-plan.md`
- **Project doc :** `PROJECT_DOC.md` (v4.2)
- **Session restart :** `memory/SESSION_RESTART.md`

## Stack
- Python 3.x, local uniquement (WS-002)
- requests, beautifulsoup4, anthropic, pydantic>=2.0, python-dotenv
- python-telegram-bot>=20.0, apscheduler>=3.10
- Claude Sonnet (supervisor + pricer), Ollama Llama 3.1 8B (analyst), Claude Haiku (fallback)
- No database, no VPS — single process on WS-002

## Architecture (Locked)
```
run.py (entry point + PID lockfile)
  ├── telegram_bot.py (polling, French UI, 8 commands)
  ├── scheduler.py (APScheduler, configurable 1h-1w)
  └── agent_supervisor.py (Claude Sonnet tool_use loop, 8 tools, max 20 iter)
        ├── scraper_lbc.py / scraper_lacentrale.py / scraper_leparking.py / scraper_autoscout.py
        ├── agent_analyst.py (Ollama 8B → Haiku fallback, scoring rubric 100pts)
        ├── agent_pricer.py (Claude Sonnet, market price + French nego messages)
        ├── hitl.py (terminal HITL for Jerome)
        └── state.py (_IQ/state.json)
```

## Data Models (Pydantic v2)
`RawListing` → `ScoredListing` → `PricedListing` — no raw dicts cross module boundaries.

## 4 Scrapers
LeBonCoin, La Centrale, Le Parking, AutoScout24 — all run in parallel (threading)

## Langue UI Telegram
**TOUT le Telegram bot est en français** — noms de commandes, réponses, menus, alertes.
Commandes: `/chercher`, `/liste`, `/approuver`, `/rejeter`, `/details`, `/intervalle`, `/statut`
Ne JAMAIS introduire de texte anglais dans l'interface Telegram.

## Interfaces
- **Telegram bot** — Friend primary (shortlists, approve/reject, alerts), Jerome mirror (oversight). **UI 100% français.**
- **Terminal CLI** — Dev/debug for Jerome
- **Scheduler** — APScheduler, configurable 1h-1w via Telegram `/intervalle`

## Commandes
```
python run.py           # Full: bot + scheduler + CLI (PID lockfile prevents 409 Conflict)
python run.py scrape    # Scrape only
python run.py analyze   # Analyze latest scrape
python run.py price     # Price latest approved shortlist
python run.py status    # Show pipeline state
python -m pytest tests/ -v   # All 263 tests
```

## PID Lockfile
`_IQ/bot.pid` prevents multiple bot instances (409 Conflict).
`_kill_old_instance()` → SIGTERM → 3s → SIGKILL. `_write_pid()` + `atexit` cleanup.

## Key Constraints
- Scoring rubric: 100pts (price 30, mileage 20, year 15, proximity 15, condition 10, transmission 10)
- Distance from Orly (48.7262, 2.3652): PRIME <20km, NEAR 20-30, FAR 30-40, REMOTE >40
- Cross-platform dedup: `(title_normalized, price, year, city_normalized)`
- Global numbering: pro 1..N, private N+1..M (consistent across Telegram + terminal)
- Friend chat ID currently = Jerome's (8595953102) — needs update for friend's real ID

## Not a git repo
This project is not currently tracked in git.
