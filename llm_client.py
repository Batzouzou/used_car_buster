"""Unified LLM client: LM Studio (local) + Anthropic (cloud) with auto-fallback."""
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import anthropic
import requests

from config import (
    ANTHROPIC_API_KEY, LM_STUDIO_BASE_URL, LM_STUDIO_MODEL, LLM_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

FALLBACK_CHAINS = {
    "local": ["lm_studio", "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
    "haiku": ["claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
    "sonnet": ["claude-sonnet-4-20250514"],
}


@dataclass
class LLMResponse:
    text: str
    model_used: str
    raw: Any


class LLMClient:
    """Unified interface for LM Studio and Anthropic models."""

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
                    if model == "lm_studio":
                        return self._query_lm_studio(messages, system)
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

    def _query_lm_studio(
        self, messages: list[dict], system: str | None = None
    ) -> LLMResponse:
        """Query LM Studio local LLM via OpenAI-compatible /v1/chat/completions."""
        lm_messages = []
        if system:
            lm_messages.append({"role": "system", "content": system})
        lm_messages.extend(messages)

        resp = requests.post(
            f"{LM_STUDIO_BASE_URL}/v1/chat/completions",
            json={"model": LM_STUDIO_MODEL, "messages": lm_messages},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            model_used="lm_studio",
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
