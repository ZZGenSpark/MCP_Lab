"""Reflection: an LLM critique plus a deterministic fact check."""

from __future__ import annotations

import json
import re

from equipment_host.guardrails import Evidence
from equipment_host.llm import LLM
from equipment_host.prompts import reflection_prompt

_PROMISE = re.compile(
    r"\b(will ship|ships tomorrow|ship tomorrow|delivery date|guaranteed to arrive)\b",
    re.IGNORECASE,
)
_PROMISE_SENTENCE = re.compile(
    r"[^.?!]*\b(will ship|ships tomorrow|ship tomorrow|delivery date|"
    r"guaranteed to arrive)\b[^.?!]*[.?!]?",
    re.IGNORECASE,
)
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def fact_check(draft: str, decision: str, evidence: Evidence) -> list[str]:
    """Flag promises and claims that the observations do not support."""
    issues: list[str] = []
    blob = json.dumps([item.result for item in evidence.observations])
    if _PROMISE.search(draft):
        issues.append("The draft promises a delivery that no observation confirms.")
    for day in _DATE.findall(draft):
        if day not in blob:
            issues.append(f"The date {day} does not appear in an observation.")
    eligibility = evidence.last("check_request_eligibility")
    eligible = eligibility.get("eligible") if isinstance(eligibility, dict) else None
    if decision == "approve" and eligible is not True:
        issues.append("The draft approves without an eligible result.")
    if decision == "deny" and eligible is True:
        issues.append("The draft denies a request the policy marked eligible.")
    if decision == "escalate" and eligible is False:
        issues.append("The draft escalates a categorical denial.")
    return issues


def reflect(
    draft: str, decision: str, evidence: Evidence, llm: LLM
) -> dict[str, object]:
    """Return verdict, issues, and final_text. A fact-check hit forces revised."""
    issues = fact_check(draft, decision, evidence)
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
    )
    _llm_verdict, llm_issues, _llm_text = _parse_critique(critique)
    if issues:
        return {
            "verdict": "revised",
            "issues": _merge(issues, llm_issues),
            "final_text": _revise(draft),
            "draft": draft,
            "critique": critique,
        }
    return {
        "verdict": "confirmed",
        "issues": [],
        "final_text": draft,
        "draft": draft,
        "critique": critique,
    }


def _revise(draft: str) -> str:
    text = _PROMISE_SENTENCE.sub("", draft)
    text = re.sub(r"\s+", " ", text).strip()
    if not text.endswith("."):
        text = f"{text}." if text else "The decision stands."
    return f"{text} No delivery date is confirmed."


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
