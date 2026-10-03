"""Ollama chat client and a scripted stand-in for tests."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from config import LLMConfig

# A reasoning model may still wrap a reply in <think>...</think>. Drop it.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatReply:
    """One model turn: prose, structured tool calls, or both."""

    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


class LLM(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatReply:
        """Return the next assistant turn. Tools are Ollama function definitions."""


class ScriptedLLM:
    """Replies in order. Tests use this instead of Ollama."""

    def __init__(self, replies: list[ChatReply | str]) -> None:
        self._replies = list(replies)
        self.sent: list[list[dict[str, Any]]] = []
        self.tools: list[list[dict[str, Any]] | None] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatReply:
        self.sent.append(list(messages))
        self.tools.append(tools)
        if not self._replies:
            raise RuntimeError("scripted LLM has no replies left")
        reply = self._replies.pop(0)
        if isinstance(reply, str):
            return ChatReply(content=reply)
        return reply


def ollama_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn MCP tool specs into the function list Ollama expects."""
    converted: list[dict[str, Any]] = []
    for tool in tools:
        schema = tool.get("input_schema") or {"type": "object", "properties": {}}
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "parameters": schema,
                },
            }
        )
    return converted


def chat_reply_from_message(message: dict[str, Any]) -> ChatReply:
    """Read content and tool_calls from one Ollama message."""
    content = message.get("content") or ""
    if not isinstance(content, str):
        content = str(content)
    calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        function = raw.get("function") if isinstance(raw, dict) else None
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        calls.append(
            ToolCall(name=name, arguments=_arguments(function.get("arguments")))
        )
    content = _THINK_BLOCK.sub("", content)
    return ChatReply(content=content.strip(), tool_calls=tuple(calls))


def _arguments(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    return {}


class OllamaLLM:
    """POST /api/chat with tools. On a connection failure, try the fallback once."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        temperature: float = 0.0,
        timeout: int = 60,
        fallback_model: str | None = None,
        think: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.fallback_model = fallback_model
        self.think = think

    @classmethod
    def from_config(cls, llm: LLMConfig) -> OllamaLLM:
        """Build the client from the `llm` section of the central config."""
        return cls(
            llm.base_url,
            llm.model,
            temperature=llm.temperature,
            timeout=llm.timeout_seconds,
            fallback_model=llm.fallback_model,
            think=llm.think,
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatReply:
        try:
            return self._post(self.model, messages, tools)
        except (OSError, urllib.error.URLError, TimeoutError):
            if self.fallback_model and self.fallback_model != self.model:
                return self._post(self.fallback_model, messages, tools)
            raise

    def _post(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> ChatReply:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
            # Ollama accepts think: false on models that cannot think too.
            "think": self.think,
        }
        if tools:
            payload["tools"] = tools
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        message = parsed.get("message")
        if not isinstance(message, dict):
            raise TypeError(f"Ollama returned no message for {model}")
        return chat_reply_from_message(message)


# Kept so a caller can build a reply without importing the dataclass fields twice.
def tool_reply(name: str, arguments: dict[str, Any], thought: str = "") -> ChatReply:
    return ChatReply(content=thought, tool_calls=(ToolCall(name, arguments),))
