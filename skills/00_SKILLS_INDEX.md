---
name: iq-skills-index
description: Routing index for Toyota iQ Auto Search System v2 skills. Load this first in every Claude Code session for this project.
version: 1.0
updated: 2026-03-28
project: G:\Downloads\_search_vehicles\
---

# IQ AUTO SEARCH — SKILLS INDEX

## Auto-load rules (add to CLAUDE.md)

```
At session start, load: /skills/00_SKILLS_INDEX.md
For scraper tasks: load skill_02_iq-scraping.md
For agent tasks: load skill_03_iq-agents.md
For LLM/Ollama tasks: load skill_04_iq-llm.md
For data/Pydantic tasks: load skill_05_iq-data.md
For testing: load skill_06_iq-testing.md
Always active: skill_01_iq-system.md
```

## Skill map

| File | Skill | Load when |
|------|-------|-----------|
| skill_01_iq-system.md | System context | ALWAYS |
| skill_02_iq-scraping.md | Scraper + anti-detection | scraping, LBC, La Centrale, HTML parsing |
| skill_03_iq-agents.md | Agent rules + prompts | supervisor, analyst, pricer, HITL |
| skill_04_iq-llm.md | LLM strategy | Ollama, Claude API, fallback chain |
| skill_05_iq-data.md | Data models + state | Pydantic, scoring, state.json, output files |
| skill_06_iq-testing.md | Test strategy | pytest, fixtures, TDD, Green/Red gates |

## Project path

```
G:\Downloads\_search_vehicles\
```

## Key constraints (always apply)

- Transmission filter = AUTOMATIC ONLY. Manual = EXCLUDE (score -1). No exceptions.
- Budget cap: 5,000 EUR. Over = EXCLUDE.
- Distance reference: Orly (48.7262, 2.3652).
- Python 3.11. No raw dicts — Pydantic everywhere.
- Secrets in .env only. Never in code or logs.
- Local LLM first (Ollama). Cloud fallback only on failure.
