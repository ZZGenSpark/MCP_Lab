"""Shared reply shapes for full-stack tests."""

from __future__ import annotations

import json


def action(name: str, arguments: dict, thought: str = "Check the records.") -> str:
    return f"Thought: {thought}\nAction: {name} {json.dumps(arguments)}"


def final(
    decision: str,
    reason: str | None,
    text: str,
    thought: str = "Decide from the observations.",
) -> str:
    body = {"decision": decision, "reason_code": reason, "text": text}
    return f"Thought: {thought}\nFinal: {json.dumps(body)}"


def reflection(text: str, verdict: str = "confirmed") -> str:
    return json.dumps({"verdict": verdict, "issues": [], "final_text": text})
