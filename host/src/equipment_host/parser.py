"""Parse one model reply into an Action, a Final, or Malformed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Action:
    name: str
    arguments: dict[str, Any]
    thought: str


@dataclass(frozen=True)
class Final:
    decision: str
    reason_code: str | None
    text: str
    thought: str


@dataclass(frozen=True)
class Malformed:
    message: str


def parse_reply(raw: str) -> Action | Final | Malformed:
    """Accept a Thought plus either Action or Final. Anything else is malformed."""
    text = raw.strip()
    thought = _thought(text)
    action_at = text.find("Action:")
    final_at = text.find("Final:")
    if action_at == -1 and final_at == -1:
        return Malformed("missing Action or Final")
    if final_at != -1 and (action_at == -1 or final_at < action_at):
        return _final(text[final_at + len("Final:") :], thought)
    return _action(text[action_at + len("Action:") :], thought)


def _thought(text: str) -> str:
    marker = "Thought:"
    start = text.find(marker)
    if start == -1:
        return ""
    rest = text[start + len(marker) :]
    line = rest.split("\n", 1)[0]
    return line.strip()


def _action(body: str, thought: str) -> Action | Malformed:
    brace = body.find("{")
    if brace == -1:
        return Malformed("Action is missing a JSON object")
    name = body[:brace].strip()
    if not name or any(ch.isspace() for ch in name):
        return Malformed("Action tool name is missing")
    try:
        arguments = json.loads(body[brace:])
    except json.JSONDecodeError:
        return Malformed("Action JSON is invalid")
    if not isinstance(arguments, dict):
        return Malformed("Action JSON must be an object")
    return Action(name=name, arguments=arguments, thought=thought)


def _final(body: str, thought: str) -> Final | Malformed:
    brace = body.find("{")
    if brace == -1:
        return Malformed("Final is missing a JSON object")
    try:
        payload = json.loads(body[brace:])
    except json.JSONDecodeError:
        return Malformed("Final JSON is invalid")
    if not isinstance(payload, dict):
        return Malformed("Final JSON must be an object")
    decision = payload.get("decision")
    if decision not in {"approve", "deny", "escalate"}:
        return Malformed("Final decision must be approve, deny, or escalate")
    reason = payload.get("reason_code")
    if reason is not None and not isinstance(reason, str):
        return Malformed("reason_code must be a string or null")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return Malformed("Final text must be a non-empty string")
    return Final(
        decision=decision,
        reason_code=reason,
        text=text.strip(),
        thought=thought,
    )
