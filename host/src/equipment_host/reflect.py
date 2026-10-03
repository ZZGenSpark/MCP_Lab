"""Reflection: a second model call judges the draft, then values are grounded."""

from __future__ import annotations

import json
import re

from equipment_host.guardrails import Evidence
from equipment_host.llm import LLM
from equipment_host.prompts import reflection_prompt

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_ID = re.compile(r"\b[A-Za-z]{1,8}-?\d{2,}\b")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_SENTENCE = re.compile(r"[^.!?]+[.!?]?")
_FALLBACK = "The decision stands."


def reflect(
    draft: str, decision: str, evidence: Evidence, llm: LLM
) -> dict[str, object]:
    """Ask the model to confirm or revise, then drop values the tools never returned."""
    observations = json.dumps(
        [{"tool": item.tool, "result": item.result} for item in evidence.observations],
        default=str,
    )
    critique = llm.complete(
        [
            {
                "role": "user",
                "content": reflection_prompt(draft, decision, observations),
            }
        ]
    ).content
    verdict, issues, final_text = _parse_critique(critique)
    if verdict == "revised" and final_text:
        text = final_text
    else:
        text = draft
        if verdict != "revised":
            verdict = "confirmed"
    text, grounding = _ground(text, decision, evidence)
    if grounding:
        verdict = "revised"
        issues = _merge(issues, grounding)
    return {
        "verdict": verdict,
        "issues": issues,
        "final_text": text,
        "draft": draft,
        "critique": critique,
    }


def _ground(text: str, decision: str, evidence: Evidence) -> tuple[str, list[str]]:
    """Return the reply and issues after removing unsupported values."""
    allowed = _allowed(evidence)
    missing = [token for token in _tokens(text) if not _supported(token, allowed)]
    issues = [
        f"The reply states {token}, which is not in an observation."
        for token in missing
    ]
    grounded = _drop_sentences(text, missing) if missing else text.strip()
    mismatch = _decision_issue(decision, evidence)
    if mismatch is not None:
        issues.append(mismatch)
    return grounded, issues


def _allowed(evidence: Evidence) -> list[str]:
    values: list[str] = []
    for item in evidence.observations:
        values.extend(_scalars(item.arguments))
        values.extend(_scalars(item.result))
    return values


def _scalars(value: object) -> list[str]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found: list[str] = []
        for item in value.values():
            found.extend(_scalars(item))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for item in value:
            found.extend(_scalars(item))
        return found
    return []


def _tokens(text: str) -> list[str]:
    dates = _DATE.findall(text)
    identifiers = _ID.findall(text)
    remainder = _ID.sub(" ", _DATE.sub(" ", text))
    numbers = _NUMBER.findall(remainder)
    found: list[str] = []
    for token in dates + identifiers + numbers:
        if token not in found:
            found.append(token)
    return found


def _supported(token: str, allowed: list[str]) -> bool:
    pattern = re.compile(rf"\b{re.escape(token)}\b")
    return any(token == value or pattern.search(value) for value in allowed)


def _drop_sentences(text: str, missing: list[str]) -> str:
    kept: list[str] = []
    for match in _SENTENCE.finditer(text.strip()):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        if any(re.search(rf"\b{re.escape(token)}\b", sentence) for token in missing):
            continue
        kept.append(sentence)
    if not kept:
        return _FALLBACK
    joined = " ".join(kept).strip()
    if joined[-1] not in ".!?":
        joined += "."
    return joined


def _decision_issue(decision: str, evidence: Evidence) -> str | None:
    eligibility = evidence.last("check_request_eligibility")
    if not isinstance(eligibility, dict):
        return None
    eligible = eligibility.get("eligible")
    if decision == "approve" and eligible is not True:
        return "The decision approve does not match eligible true."
    if decision == "deny" and eligible is True:
        return "The decision deny does not match eligible true."
    if decision == "escalate" and eligible is False:
        return "The decision escalate does not match eligible false."
    return None


def _parse_critique(raw: str) -> tuple[str, list[str], str]:
    brace = raw.find("{")
    if brace == -1:
        return ("confirmed", [], "")
    try:
        payload = json.loads(raw[brace:])
    except json.JSONDecodeError:
        return ("confirmed", [], "")
    if not isinstance(payload, dict):
        return ("confirmed", [], "")
    verdict = payload.get("verdict")
    if verdict not in {"confirmed", "revised"}:
        verdict = "confirmed"
    issues = payload.get("issues")
    if not isinstance(issues, list):
        issues = []
    text = payload.get("final_text")
    return (
        verdict,
        [str(item) for item in issues],
        text.strip() if isinstance(text, str) else "",
    )


def _merge(primary: list[str], extra: list[str]) -> list[str]:
    merged = list(primary)
    for item in extra:
        if item not in merged:
            merged.append(item)
    return merged
