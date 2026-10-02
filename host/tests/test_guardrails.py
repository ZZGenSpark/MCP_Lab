"""Each decision against the observations that should accept or reject it."""

from __future__ import annotations

import pytest
from equipment_host.guardrails import Evidence, evaluate

RETRIES = 1


def _ok(eligible: object, reason: str | None, rule: str = "rule") -> dict:
    return {
        "ok": True,
        "eligible": eligible,
        "reason_code": reason,
        "rule": rule,
    }


def _err(code: str) -> dict:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": code,
            "field": "employee_id",
            "retryable": False,
            "hint": "Check the id.",
        },
    }


def _evidence(*rows: tuple[str, dict]) -> Evidence:
    evidence = Evidence()
    for tool, result in rows:
        evidence.add(tool, {"n": len(evidence.observations)}, result)
    return evidence


@pytest.mark.parametrize(
    ("decision", "reason", "rows", "accepted"),
    [
        (
            "approve",
            None,
            [("check_request_eligibility", _ok(True, None))],
            True,
        ),
        (
            "approve",
            None,
            [("check_request_eligibility", _ok(False, "ROLE_NOT_ELIGIBLE"))],
            False,
        ),
        (
            "deny",
            "ROLE_NOT_ELIGIBLE",
            [("check_request_eligibility", _ok(False, "ROLE_NOT_ELIGIBLE"))],
            True,
        ),
        (
            "deny",
            "LIMIT_REACHED",
            [("check_request_eligibility", _ok(False, "LIMIT_REACHED"))],
            True,
        ),
        (
            "deny",
            "ROLE_NOT_ELIGIBLE",
            [("check_request_eligibility", _ok(True, None))],
            False,
        ),
        (
            "deny",
            "EMPLOYEE_NOT_FOUND",
            [("get_employee_info", _err("EMPLOYEE_NOT_FOUND"))],
            False,
        ),
        (
            "escalate",
            "WITHIN_WINDOW_WITH_REASON",
            [
                (
                    "check_request_eligibility",
                    _ok("unclear", "WITHIN_WINDOW_WITH_REASON"),
                ),
                (
                    "flag_for_human_review",
                    {"ok": True, "ticket_id": "REV-0001", "status": "pending_review"},
                ),
            ],
            True,
        ),
        (
            "escalate",
            "TENURE_UNDER_90_DAYS",
            [("check_request_eligibility", _ok("unclear", "TENURE_UNDER_90_DAYS"))],
            False,
        ),
        (
            "escalate",
            "NOT_A_CODE",
            [("check_request_eligibility", _ok("unclear", "NOT_A_CODE"))],
            False,
        ),
    ],
)
def test_guardrail_table(
    decision: str,
    reason: str | None,
    rows: list[tuple[str, dict]],
    accepted: bool,
) -> None:
    result = evaluate(decision, reason, _evidence(*rows), max_tool_retries=RETRIES)
    assert result.accepted is accepted


def test_definite_error_is_accepted_only_after_one_retry() -> None:
    once = Evidence()
    once.add("get_employee_info", {"employee_id": "E9999"}, _err("EMPLOYEE_NOT_FOUND"))
    denied_early = evaluate(
        "deny", "EMPLOYEE_NOT_FOUND", once, max_tool_retries=RETRIES
    )
    assert denied_early.accepted is False
    twice = Evidence()
    twice.add("get_employee_info", {"employee_id": "E9999"}, _err("EMPLOYEE_NOT_FOUND"))
    twice.add("get_employee_info", {"employee_id": "E9999"}, _err("EMPLOYEE_NOT_FOUND"))
    denied = evaluate("deny", "EMPLOYEE_NOT_FOUND", twice, max_tool_retries=RETRIES)
    assert denied.accepted is True


def test_escalating_an_unknown_employee_overrides_to_deny() -> None:
    evidence = Evidence()
    evidence.add(
        "get_employee_info", {"employee_id": "E9999"}, _err("EMPLOYEE_NOT_FOUND")
    )
    result = evaluate(
        "escalate",
        "VAGUE_REQUEST",
        evidence,
        max_tool_retries=RETRIES,
    )
    assert result.accepted is False
    assert result.override_decision == "deny"
    assert result.override_reason == "EMPLOYEE_NOT_FOUND"
