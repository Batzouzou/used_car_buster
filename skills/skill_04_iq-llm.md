---
name: iq-llm
description: LLM client architecture, Ollama integration, Claude API usage, fallback chain, cost strategy, and model selection for the IQ Auto Search system. Load for any LLM, Ollama, or API task.
version: 1.0
updated: 2026-03-28
load: llm | ollama | claude api | fallback | model | tokens | cost
---

# SKILL 04 — LLM STRATEGY

## Model assignment

| Agent | Primary | Fallback | Reason |
|-------|---------|----------|--------|
| Supervisor | Claude Sonnet | — | Tool-use, orchestration, reasoning |
| Analyst | Ollama llama3.1:8b | Claude Haiku | High volume, structured scoring, free |
| Pricer | Claude Sonnet | Claude Haiku | Nuanced French, negotiation quality |

## Cost logic

~60 total iQ listings, likely <20 automatic. Analyst runs on ALL listings. Local = free.
Claude Sonnet only for Supervisor + Pricer (low call count). Haiku as emergency fallback only.

## llm_client.py — unified interface

```python
def query_llm(
    prompt: str,
    agent: str = "analyst",    # "supervisor" | "analyst" | "pricer"
    system: str = None,
    json_mode: bool = False
) -> str:
    """Route to correct model with automatic fallback."""
    if agent == "analyst":
        return _query_ollama(prompt, system) or _query_claude_haiku(prompt, system)
    else:
        return _query_claude_sonnet(prompt, system)
```

## Ollama integration

```python
def _query_ollama(prompt: str, system: str = None, model: str = "llama3.1:8b") -> str | None:
    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}    # low temp for structured output
        }
        if system:
            payload["system"] = system
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["response"]
    except Exception as e:
        logger.warning(f"Ollama failed: {e}")
        return None    # triggers fallback
```

## Claude API integration

```python
import anthropic
client = anthropic.Anthropic()    # reads ANTHROPIC_API_KEY from env

def _query_claude_sonnet(prompt: str, system: str = None) -> str:
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system or "You are a helpful assistant.",
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

def _query_claude_haiku(prompt: str, system: str = None) -> str:
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=system or "You are a helpful assistant.",
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text
```

## RAM requirements (WS-002 — 32GB, upgrading to 64GB)

| Model | VRAM | RAM (CPU offload) | Quality |
|-------|------|-------------------|---------|
| llama3.1:8b Q4_K_M | 6GB | ~10GB | Sufficient for scoring |
| llama3.1:70b Q4_K_M | n/a | ~42GB | Better — available at 64GB |

At 32GB: use 8b. After RAM upgrade: test 70b for analyst quality improvement.

## JSON extraction from LLM output

```python
import json, re

def extract_json(raw: str) -> dict:
    """Strip markdown fences, extract first valid JSON object."""
    clean = re.sub(r"```(?:json)?", "", raw).strip()
    # find first { ... }
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        raise ValueError("No JSON found in LLM output")
    return json.loads(match.group())
```

## Rate limits

- Anthropic API: no hard rate limit at typical usage. Use structlog to track call count.
- Ollama: local, no limit. Timeout 120s per call is safe for 8b model.

## Gotchas

- Ollama must be running before starting the system: `ollama serve` (background process).
- First call after model pull is slow (loading weights). Subsequent calls fast.
- Temperature MUST be low (0.1) for analyst — higher temp → JSON format breaks.
- Never pass ANTHROPIC_API_KEY in code. Only via `.env` + `python-dotenv`.
