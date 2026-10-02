"""Ollama chat client and a scripted stand-in for tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol


class LLM(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return the next assistant message."""


class ScriptedLLM:
    """Replies in order. Tests use this instead of Ollama."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.sent: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.sent.append(list(messages))
        if not self._replies:
            raise RuntimeError("scripted LLM has no replies left")
        return self._replies.pop(0)


class OllamaLLM:
    """POST /api/chat. On a connection failure, try the fallback model once."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        temperature: float = 0.0,
        timeout: int = 60,
        fallback_model: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.fallback_model = fallback_model

    def complete(self, messages: list[dict[str, str]]) -> str:
        try:
            return self._post(self.model, messages)
        except (OSError, urllib.error.URLError, TimeoutError):
            if self.fallback_model and self.fallback_model != self.model:
                return self._post(self.fallback_model, messages)
            raise

    def _post(self, model: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        content = parsed.get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"Ollama returned no content for {model}")
        return content
