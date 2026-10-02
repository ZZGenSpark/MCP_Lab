"""Deterministic fact check, with the model critique as a second opinion."""

from __future__ import annotations

from equipment_host.guardrails import Evidence
from equipment_host.llm import ScriptedLLM
from equipment_host.reflect import fact_check, reflect


def _evidence() -> Evidence:
    evidence = Evidence()
    evidence.add(
        "check_request_eligibility",
        {"employee_id": "E1001", "item": "monitor"},
        {
            "ok": True,
            "eligible": True,
            "reason_code": None,
            "rule": "standard may hold 1 monitor",
            "issued_on": "2020-01-15",
        },
    )
    return evidence


def test_will_ship_is_revised_even_if_the_model_confirms() -> None:
    draft = "Approved. The monitor will ship tomorrow."
    llm = ScriptedLLM(
        ['{"verdict": "confirmed", "issues": [], "final_text": "' + draft + '"}']
    )
    reviewed = reflect(draft, "approve", _evidence(), llm)
    assert reviewed["verdict"] == "revised"
    assert "will ship" not in str(reviewed["final_text"]).lower()
    assert "No delivery date is confirmed." in str(reviewed["final_text"])


def test_unsupported_date_is_flagged() -> None:
    issues = fact_check(
        "The monitor was issued on 2099-01-01.",
        "approve",
        _evidence(),
    )
    assert any("2099-01-01" in issue for issue in issues)


def test_faithful_draft_is_confirmed() -> None:
    draft = "Approved. standard may hold 1 monitor."
    llm = ScriptedLLM(
        [f'{{"verdict": "confirmed", "issues": [], "final_text": {draft!r}}}']
    )
    reviewed = reflect(draft, "approve", _evidence(), llm)
    assert reviewed["verdict"] == "confirmed"
    assert reviewed["final_text"] == draft
    assert reviewed["issues"] == []
