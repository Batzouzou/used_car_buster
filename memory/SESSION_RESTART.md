# Toyota iQ Search — Session Restart Brief

**Last verified:** 2026-03-28
**Tests:** 263/263 passed (66.86s) — verified fresh this session

## What This Project Is

Agentic car search tool for Jerome's friend — find a Toyota iQ automatic in France.
Single long-running process: Telegram bot + APScheduler + Claude Sonnet supervisor agent.
Pipeline: scrape 4 platforms → LLM analysis → HITL (Telegram + terminal) → pricing + nego messages.

## Current State

- **Fully implemented:** 16 source files (~2,200 lines), 17 test files (~2,800 lines)
- **All 263 tests pass** with mocks — no real scraping/LLM calls yet
- **Never run live** — bot polled Telegram briefly on 2026-03-28 but no scrape executed
- **`_IQ/raw_listings_20260328.json`** is empty `[]`
- **Not a git repo**

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | Entry point + PID lockfile |
| `agent_supervisor.py` | Supervisor agent (Claude Sonnet tool_use loop, 8 tools) |
| `telegram_bot.py` | Telegram bot (French UI, 8 commands) |
| `config.py` | All config from `.env` |
| `models.py` | Pydantic v2: RawListing → ScoredListing → PricedListing |
| `state.py` | JSON state persistence at `_IQ/state.json` |
| `PROJECT_DOC.md` | Full documentation (v4.2) |
| `CLAUDE.md` | Project instructions for Claude Code |

## Important Constraints

- **This project has NOTHING to do with My Gateway Premium**
- Telegram UI is 100% French — never introduce English
- Scoring rubric: 100pts (price 30, mileage 20, year 15, proximity 15, condition 10, transmission 10)
- Distance zones from Orly (48.7262, 2.3652)
- Cross-platform dedup: (title_normalized, price, year, city_normalized)
- Friend chat ID = Jerome's for now (8595953102)

## Next Steps

1. First real scrape: `python run.py scrape` — test against live sites
2. Integration testing with real LLMs (Ollama + Anthropic)
3. Scraper HTML adjustments if sites changed
4. Get friend's real Telegram chat ID
