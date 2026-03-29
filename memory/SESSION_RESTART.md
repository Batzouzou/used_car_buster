# Toyota iQ Search — Session Restart Brief

**Last session:** 2026-03-28
**Tests:** 263/263 passed (70s) — verified end of session
**Git:** initialized, 1 commit on master, no remote

## What This Project Is

Agentic car search tool for Jerome's friend — find a Toyota iQ automatic in France.
Single long-running process: Telegram bot + APScheduler + Claude Sonnet supervisor agent.
Pipeline: scrape 4 platforms → LLM analysis → HITL (Telegram + terminal) → pricing + nego messages.

## What Happened This Session

1. **Session recovery** — read all IQ_SESSION_RECOVERY*.md files + CLAUDE.md + PROJECT_DOC.md + memory/SESSION_RESTART.md to rebuild context. The 5 numbered recovery files (IQ_SESSION_RECOVERY_1-5.md) are all identical duplicates of IQ_SESSION_RECOVERY.md (early spec from March 21).
2. **Ran full test suite** — 263/263 passed (65-70s), confirming codebase is stable.
3. **Git initialized** — `git init` in `G:\Downloads\_search_vehicles\`. Updated `.gitignore` to also exclude `_IQ/` (whole dir), `*.pdf`, `.coverage`, `.claude/`. First commit `d0b8999` — 48 files, 10,231 lines. Excluded: duplicate IQ_SESSION_RECOVERY_1-5.md, PDFs, .env, _IQ/ outputs.
4. **PROJECT_DOC.md updated** to v4.3 — added git repo status, exact Anthropic model IDs (`claude-haiku-4-5-20251001`, `claude-sonnet-4-20250514`). Code-doc skill verified all prompts, env vars, and architecture match actual code.
5. **PROJECT_DOC.md has unstaged changes** — the v4.2→v4.3 update is not yet committed.

## Current State

- **263 tests pass** with mocks — no real scraping/LLM calls yet
- **Never run live** — `_IQ/raw_listings_20260328.json` is empty `[]`
- **Git:** 1 commit `d0b8999` on master, no remote. `PROJECT_DOC.md` modified but not committed.
- **Untracked:** IQ_SESSION_RECOVERY_1-5.md (duplicates, intentionally excluded from git)
- **Not a remote repo** — no GitHub/GitLab push yet

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | Entry point + PID lockfile |
| `agent_supervisor.py` | Supervisor agent (Claude Sonnet tool_use loop, 8 tools, max 20 iter) |
| `telegram_bot.py` | Telegram bot (French UI, 8 commands) |
| `config.py` | All config from `.env` |
| `models.py` | Pydantic v2: RawListing → ScoredListing → PricedListing |
| `state.py` | JSON state persistence at `_IQ/state.json` |
| `llm_client.py` | Unified LLM: Ollama → Haiku → Sonnet fallback chain |
| `PROJECT_DOC.md` | Full documentation (v4.3) |
| `CLAUDE.md` | Project instructions for Claude Code |

## Important Constraints

- **This project has NOTHING to do with My Gateway Premium**
- Telegram UI is 100% French — never introduce English
- Scoring rubric: 100pts (price 30, mileage 20, year 15, proximity 15, condition 10, transmission 10)
- Distance zones from Orly (48.7262, 2.3652)
- Cross-platform dedup: (title_normalized, price, year, city_normalized)
- Friend chat ID = Jerome's for now (8595953102)
- Model IDs: Haiku = `claude-haiku-4-5-20251001`, Sonnet = `claude-sonnet-4-20250514`

## Pending Work (not committed)

- `PROJECT_DOC.md` v4.3 update (git repo info + model IDs) — needs `git add PROJECT_DOC.md && git commit`

## Next Steps

1. **Commit PROJECT_DOC.md v4.3 update**
2. **First real scrape:** `python run.py scrape` — test against live sites
3. **Integration testing** with real LLMs (Ollama + Anthropic API)
4. **Scraper HTML adjustments** if sites changed their structure
5. **Get friend's real Telegram chat ID** (currently using Jerome's: 8595953102)
6. **(Optional)** Push to GitHub remote
