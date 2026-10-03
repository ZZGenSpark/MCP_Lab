"""Ollama message parsing for structured tool calls, and the request it sends."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any, Self

import pytest
from equipment_host import llm as llm_module
from equipment_host.llm import (
    OllamaLLM,
    ToolCall,
    chat_reply_from_message,
    ollama_tools,
)

from config import LLMConfig


class _Response(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _capture(monkeypatch: pytest.MonkeyPatch, content: str = "ok") -> list[dict]:
    sent: list[dict] = []

    def fake_urlopen(request: Any, timeout: float) -> _Response:
        sent.append({"body": json.loads(request.data), "timeout": timeout})
        return _Response(json.dumps({"message": {"content": content}}).encode())

    monkeypatch.setattr(llm_module.urllib.request, "urlopen", fake_urlopen)
    return sent


def test_request_turns_thinking_off_by_default(monkeypatch) -> None:
    sent = _capture(monkeypatch)
    OllamaLLM("http://ollama:11434/", "qwen3:8b").complete(
        [{"role": "user", "content": "hi"}]
    )
    body = sent[0]["body"]
    assert body["model"] == "qwen3:8b"
    assert body["think"] is False
    assert body["stream"] is False
    assert "tools" not in body


def test_think_setting_is_sent_as_configured(monkeypatch) -> None:
    sent = _capture(monkeypatch)
    OllamaLLM("http://ollama:11434", "qwen3:8b", think=True).complete([])
    assert sent[0]["body"]["think"] is True


def test_tools_are_sent_when_given(monkeypatch) -> None:
    sent = _capture(monkeypatch)
    tools = [{"type": "function", "function": {"name": "get_employee_info"}}]
    OllamaLLM("http://ollama:11434", "qwen3:8b").complete([], tools)
    assert sent[0]["body"]["tools"] == tools


def test_from_config_carries_every_llm_setting(monkeypatch) -> None:
    sent = _capture(monkeypatch)
    cfg = LLMConfig(
        base_url="http://ollama:11434/",
        model="qwen3:8b",
        temperature=0.25,
        timeout_seconds=7,
        think=False,
    )
    client = OllamaLLM.from_config(cfg)
    client.complete([])
    assert sent[0]["timeout"] == 7
    assert sent[0]["body"]["options"] == {"temperature": 0.25}
    assert sent[0]["body"]["think"] is False
    assert client.fallback_model == cfg.fallback_model


def test_connection_failure_falls_back_to_the_other_model(monkeypatch) -> None:
    models: list[str] = []

    def fake_urlopen(request: Any, timeout: float) -> _Response:
        model = json.loads(request.data)["model"]
        models.append(model)
        if model == "qwen3:8b":
            raise urllib.error.URLError("refused")
        return _Response(json.dumps({"message": {"content": "from mistral"}}).encode())

    monkeypatch.setattr(llm_module.urllib.request, "urlopen", fake_urlopen)
    client = OllamaLLM("http://ollama:11434", "qwen3:8b", fallback_model="mistral")
    assert client.complete([]).content == "from mistral"
    assert models == ["qwen3:8b", "mistral"]


def test_think_blocks_are_removed_from_the_reply() -> None:
    reply = chat_reply_from_message(
        {"content": "<think>\nreasoning here\n</think>\nCheck the records."}
    )
    assert reply.content == "Check the records."


def test_tool_call_arguments_may_be_a_json_string() -> None:
    reply = chat_reply_from_message(
        {
            "content": "",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_employee_info",
                        "arguments": '{"employee_id": "E1001"}',
                    },
                }
            ],
        }
    )
    assert reply.tool_calls == (
        ToolCall("get_employee_info", {"employee_id": "E1001"}),
    )


def test_mcp_specs_become_ollama_functions() -> None:
    tools = ollama_tools(
        [
            {
                "name": "get_employee_info",
                "description": "Look up an employee",
                "input_schema": {
                    "type": "object",
                    "properties": {"employee_id": {"type": "string"}},
                },
            }
        ]
    )
    assert tools[0]["function"]["name"] == "get_employee_info"
    assert tools[0]["function"]["parameters"]["properties"]["employee_id"]["type"] == (
        "string"
    )
