"""Parse a decision JSON object from a model message that did not call a tool."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class Final:
    decision: str
    reason_code: str | None
    text: str
    thought: str


@dataclass(frozen=True)
class Malformed:
    message: str


def parse_decision(raw: str) -> Final | Malformed:
    """Accept a JSON object with decision, reason_code, and text."""
    text = _THINK.sub("", raw).strip()
    text = _FENCE.sub("", text).strip()
    start = text.find("{")
    if start == -1:
        return Malformed("missing decision JSON")
    try:
        payload, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return Malformed("decision JSON is invalid")
    if not isinstance(payload, dict):
        return Malformed("decision JSON must be an object")
    decision = payload.get("decision")
    if decision not in {"approve", "deny", "escalate"}:
        return Malformed("decision must be approve, deny, or escalate")
    reason = payload.get("reason_code")
    if reason is not None and not isinstance(reason, str):
        return Malformed("reason_code must be a string or null")
    body = payload.get("text")
    if not isinstance(body, str) or not body.strip():
        return Malformed("decision text must be a non-empty string")
    return Final(
        decision=decision,
        reason_code=reason,
        text=body.strip(),
        thought=text[:start].strip(),
    )
