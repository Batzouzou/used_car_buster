"""Unified LLM client: Ollama (local) + Anthropic (cloud) with auto-fallback."""
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import anthropic
import requests

from config import (
    ANTHROPIC_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL, LLM_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

FALLBACK_CHAINS = {
    "local": ["ollama", "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
    "haiku": ["claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
    "sonnet": ["claude-sonnet-4-20250514"],
}


@dataclass
class LLMResponse:
    text: str
    model_used: str
    raw: Any


class LLMClient:
    """Unified interface for Ollama and Anthropic models."""

    def __init__(self):
        self._anthropic_client = None
        if ANTHROPIC_API_KEY:
            self._anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def query(
        self,
        messages: list[dict],
        model_preference: str = "local",
        system: str | None = None,
    ) -> LLMResponse:
        """Send messages to LLM with automatic fallback chain."""
        chain = FALLBACK_CHAINS.get(model_preference, FALLBACK_CHAINS["local"])
        last_error = None

        for model in chain:
            for attempt in range(LLM_MAX_RETRIES + 1):
                try:
                    if model == "ollama":
                        return self._query_ollama(messages, system)
                    else:
                        return self._query_anthropic(messages, model, system)
                except Exception as e:
                    last_error = e
                    logger.warning(f"{model} attempt {attempt+1} failed: {e}")
                    if attempt < LLM_MAX_RETRIES:
                        time.sleep(2 ** attempt)

        raise RuntimeError(f"All LLM models failed. Last error: {last_error}")

    def query_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> dict:
        """Send messages with tool definitions (Anthropic tool_use API only)."""
        if not self._anthropic_client:
            raise RuntimeError("Anthropic API key required for tool_use")

        kwargs = {
            "model": model,
            "max_tokens": 4096,
            "messages": messages,
            "tools": tools,
        }
        if system:
            kwargs["system"] = system

        response = self._anthropic_client.messages.create(**kwargs)
        return {
            "content": response.content,
            "stop_reason": response.stop_reason,
            "model": response.model,
            "raw": response,
        }

    def _query_ollama(
        self, messages: list[dict], system: str | None = None
    ) -> LLMResponse:
        """Query Ollama local LLM via /api/chat endpoint."""
        ollama_messages = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        ollama_messages.extend(messages)

        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": ollama_messages, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(
            text=data["message"]["content"],
            model_used="ollama",
            raw=data,
        )

    def _query_anthropic(
        self, messages: list[dict], model: str, system: str | None = None
    ) -> LLMResponse:
        """Query Anthropic API."""
        if not self._anthropic_client:
            raise RuntimeError("No Anthropic API key configured")

        kwargs = {"model": model, "max_tokens": 4096, "messages": messages}
        if system:
            kwargs["system"] = system

        response = self._anthropic_client.messages.create(**kwargs)
        text = response.content[0].text if response.content else ""
        return LLMResponse(text=text, model_used=model, raw=response)
