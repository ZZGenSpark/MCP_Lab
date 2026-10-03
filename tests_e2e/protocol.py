"""Shared reply shapes for full-stack tests."""

from __future__ import annotations

import json

from equipment_host.llm import ChatReply, tool_reply


def action(
    name: str, arguments: dict, thought: str = "Check the records."
) -> ChatReply:
    return tool_reply(name, arguments, thought)


def final(
    decision: str,
    reason: str | None,
    text: str,
    thought: str = "Decide from the observations.",
) -> ChatReply:
    body = {"decision": decision, "reason_code": reason, "text": text}
    content = json.dumps(body)
    if thought:
        content = f"{thought}\n{content}"
    return ChatReply(content=content)


def reflection(
    text: str, verdict: str = "confirmed", issues: list[str] | None = None
) -> str:
    return json.dumps({"verdict": verdict, "issues": issues or [], "final_text": text})
