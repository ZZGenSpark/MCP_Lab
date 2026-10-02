"""Decision checks that run in code, beside the system prompt."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

DEFINITE_DENY = frozenset({"EMPLOYEE_NOT_FOUND", "UNKNOWN_ITEM", "UNKNOWN_ROLE"})
ESCALATE_CODES = frozenset(
    {
        "WITHIN_WINDOW_WITH_REASON",
        "TENURE_UNDER_90_DAYS",
        "DATA_CONFLICT",
        "VAGUE_REQUEST",
    }
)
RETRYABLE = frozenset({"INTERNAL_ERROR", "TRANSPORT_ERROR", "INVALID_ARGUMENT"})


@dataclass(frozen=True)
class Observation:
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]


def _canonical(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments, sort_keys=True, default=str)


@dataclass
class Evidence:
    """Tool observations collected during one request."""

    observations: list[Observation] = field(default_factory=list)

    def add(self, tool: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        self.observations.append(Observation(tool, dict(arguments), result))

    def error_count(self, tool: str, arguments: dict[str, Any]) -> int:
        key = _canonical(arguments)
        return sum(
            1
            for item in self.observations
            if item.tool == tool
            and _canonical(item.arguments) == key
            and item.result.get("ok") is False
        )

    def code_count(self, code: str) -> int:
        return sum(1 for item in self.observations if _code(item.result) == code)

    def last(self, tool: str) -> dict[str, Any] | None:
        found = self.last_observation(tool)
        return None if found is None else found.result

    def last_observation(self, tool: str) -> Observation | None:
        found = [item for item in self.observations if item.tool == tool]
        return found[-1] if found else None

    def successful_flag(self) -> dict[str, Any] | None:
        for item in reversed(self.observations):
            if item.tool == "flag_for_human_review" and item.result.get("ok") is True:
                return item.result
        return None


@dataclass(frozen=True)
class GuardrailResult:
    accepted: bool
    message: str
    override_decision: str | None = None
    override_reason: str | None = None
    override_text: str | None = None


def evaluate(
    decision: str,
    reason_code: str | None,
    evidence: Evidence,
    *,
    max_tool_retries: int,
) -> GuardrailResult:
    """Accept a decision only when the observations support it."""
    definite = _definite_code(evidence, max_tool_retries)
    if decision == "escalate" and definite is not None:
        return GuardrailResult(
            accepted=False,
            message=(
                f"Do not escalate. {definite} is a definite rejection. "
                "Deny with that code and do not open a ticket."
            ),
            override_decision="deny",
            override_reason=definite,
            override_text=_deny_text(definite, evidence),
        )
    if decision == "approve":
        return _approve(evidence)
    if decision == "deny":
        return _deny(reason_code, evidence, max_tool_retries)
    if decision == "escalate":
        return _escalate(reason_code, evidence)
    return GuardrailResult(False, "Decision must be approve, deny, or escalate.")


def evidence_decision(
    evidence: Evidence, *, max_tool_retries: int
) -> tuple[str, str | None, str]:
    """The decision the observations support after a rejected re-prompt."""
    eligibility = evidence.last("check_request_eligibility")
    if isinstance(eligibility, dict) and eligibility.get("ok") is True:
        eligible = eligibility.get("eligible")
        reason = eligibility.get("reason_code")
        rule = str(eligibility.get("rule") or "")
        if eligible is True:
            return ("approve", None, f"Approved. {rule}".strip())
        if eligible is False:
            return ("deny", _as_str(reason), f"Denied. {rule}".strip())
        ticket = evidence.successful_flag()
        if eligible == "unclear" and reason in ESCALATE_CODES and ticket is not None:
            ticket_id = ticket.get("ticket_id", "")
            return (
                "escalate",
                _as_str(reason),
                f"Escalated ({reason}) as {ticket_id}. {rule}".strip(),
            )
    definite = _any_definite(evidence)
    if definite is not None:
        return ("deny", definite, _deny_text(definite, evidence))
    if _retryable_exhausted(evidence, max_tool_retries):
        return (
            "system_fault",
            None,
            "The request could not be processed because of a system fault.",
        )
    return (
        "unresolved",
        None,
        "The request could not be decided from the tool results.",
    )


def _approve(evidence: Evidence) -> GuardrailResult:
    eligibility = evidence.last("check_request_eligibility")
    if isinstance(eligibility, dict) and eligibility.get("eligible") is True:
        return GuardrailResult(True, "approve matches eligible true")
    return GuardrailResult(
        False,
        "Approve only if the last check_request_eligibility returned eligible true.",
    )


def _deny(
    reason_code: str | None, evidence: Evidence, max_tool_retries: int
) -> GuardrailResult:
    eligibility = evidence.last("check_request_eligibility")
    if (
        isinstance(eligibility, dict)
        and eligibility.get("ok") is True
        and eligibility.get("eligible") is False
        and reason_code == eligibility.get("reason_code")
    ):
        return GuardrailResult(True, "deny matches eligible false")
    if (
        reason_code in DEFINITE_DENY
        and evidence.code_count(reason_code) > max_tool_retries
    ):
        return GuardrailResult(True, "deny matches a definite error after one retry")
    if reason_code in DEFINITE_DENY:
        return GuardrailResult(
            False,
            f"Retry the failed call once before denying with {reason_code}. "
            "Do not invent an id or item.",
        )
    return GuardrailResult(
        False,
        "Deny only with eligible false and the same reason code, or a definite "
        "error that is still failing after one retry.",
    )


def _escalate(reason_code: str | None, evidence: Evidence) -> GuardrailResult:
    if reason_code not in ESCALATE_CODES:
        return GuardrailResult(
            False,
            "Escalate only for WITHIN_WINDOW_WITH_REASON, TENURE_UNDER_90_DAYS, "
            "DATA_CONFLICT, or VAGUE_REQUEST.",
        )
    if evidence.successful_flag() is None:
        return GuardrailResult(
            False,
            "Call flag_for_human_review and wait for a ticket before escalating.",
        )
    eligibility = evidence.last("check_request_eligibility")
    if (
        isinstance(eligibility, dict)
        and eligibility.get("eligible") == "unclear"
        and eligibility.get("reason_code") == reason_code
    ):
        return GuardrailResult(True, "escalate matches an unclear policy result")
    return GuardrailResult(
        False,
        "Escalate only when check_request_eligibility returned eligible unclear "
        "with the same reason code.",
    )


def _definite_code(evidence: Evidence, max_tool_retries: int) -> str | None:
    """A definite error that has already been retried, if one is present."""
    for code in ("EMPLOYEE_NOT_FOUND", "UNKNOWN_ITEM", "UNKNOWN_ROLE"):
        if evidence.code_count(code) > max_tool_retries:
            return code
    return _any_definite(evidence)


def _any_definite(evidence: Evidence) -> str | None:
    for code in ("EMPLOYEE_NOT_FOUND", "UNKNOWN_ITEM", "UNKNOWN_ROLE"):
        if evidence.code_count(code) > 0:
            return code
    return None


def _retryable_exhausted(evidence: Evidence, max_tool_retries: int) -> bool:
    for item in evidence.observations:
        code = _code(item.result)
        if (
            code in RETRYABLE
            and evidence.error_count(item.tool, item.arguments) > max_tool_retries
        ):
            return True
    return False


def _deny_text(code: str, evidence: Evidence) -> str:
    hint = ""
    for item in reversed(evidence.observations):
        if _code(item.result) == code:
            error = item.result.get("error", {})
            hint = str(error.get("hint") or error.get("message") or "")
            break
    if code == "EMPLOYEE_NOT_FOUND":
        return f"Denied. No employee matches that id. {hint}".strip()
    if code == "UNKNOWN_ITEM":
        return f"Denied. That item is not in the catalog. {hint}".strip()
    return f"Denied. The role is not recognized. {hint}".strip()


def _code(result: dict[str, Any]) -> str | None:
    if result.get("ok") is not False:
        return None
    error = result.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
