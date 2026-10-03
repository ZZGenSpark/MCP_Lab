"""The reflection model confirms or revises the draft. Its verdict is kept."""

from __future__ import annotations

import json

from equipment_host.guardrails import Evidence
from equipment_host.llm import ScriptedLLM
from equipment_host.reflect import reflect


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


def _judge(verdict: str, text: str, issues: list[str] | None = None) -> ScriptedLLM:
    body = {
        "verdict": verdict,
        "issues": issues or [],
        "final_text": text,
    }
    return ScriptedLLM([json.dumps(body)])


def test_a_confirming_judge_keeps_the_draft_even_when_it_promises_delivery() -> None:
    draft = "Approved. The monitor will ship tomorrow."
    reviewed = reflect(draft, "approve", _evidence(), _judge("confirmed", draft))
    assert reviewed["verdict"] == "confirmed"
    assert reviewed["final_text"] == draft
    assert reviewed["issues"] == []


def test_a_revised_judgment_replaces_the_draft() -> None:
    draft = "Approved. The monitor will ship tomorrow."
    rewritten = "Approved. No delivery date is confirmed."
    issue = "The draft promises a delivery that no observation confirms."
    reviewed = reflect(
        draft, "approve", _evidence(), _judge("revised", rewritten, [issue])
    )
    assert reviewed["verdict"] == "revised"
    assert reviewed["final_text"] == rewritten
    assert reviewed["issues"] == [issue]
    assert "will ship" not in str(reviewed["final_text"]).lower()


def test_confirmed_ignores_a_different_final_text() -> None:
    draft = "Approved. standard may hold 1 monitor."
    reviewed = reflect(
        draft,
        "approve",
        _evidence(),
        _judge("confirmed", "Approved. The monitor will ship tomorrow."),
    )
    assert reviewed["verdict"] == "confirmed"
    assert reviewed["final_text"] == draft


def test_a_revised_judgment_with_no_text_keeps_the_draft() -> None:
    draft = "Approved. The monitor will ship tomorrow."
    reviewed = reflect(
        draft,
        "approve",
        _evidence(),
        _judge("revised", "  ", ["The draft promises a delivery."]),
    )
    assert reviewed["verdict"] == "revised"
    assert reviewed["final_text"] == draft


def test_malformed_critique_confirms_the_draft() -> None:
    draft = "Approved. standard may hold 1 monitor."
    reviewed = reflect(draft, "approve", _evidence(), ScriptedLLM(["not json"]))
    assert reviewed["verdict"] == "confirmed"
    assert reviewed["final_text"] == draft
    assert reviewed["issues"] == []


def test_a_date_from_an_observation_is_kept() -> None:
    draft = "Approved. The monitor was issued on 2020-01-15."
    reviewed = reflect(draft, "approve", _evidence(), _judge("confirmed", draft))
    assert reviewed["verdict"] == "confirmed"
    assert reviewed["final_text"] == draft


def test_an_unsupported_date_is_removed_even_when_the_judge_confirms() -> None:
    draft = "Approved. The monitor was issued on 2099-01-01."
    reviewed = reflect(draft, "approve", _evidence(), _judge("confirmed", draft))
    assert reviewed["verdict"] == "revised"
    assert "2099-01-01" not in str(reviewed["final_text"])
    assert str(reviewed["final_text"]).startswith("Approved.")
    assert any("2099-01-01" in str(issue) for issue in reviewed["issues"])


def test_an_unsupported_id_is_removed() -> None:
    draft = "Approved for E9999."
    reviewed = reflect(draft, "approve", _evidence(), _judge("confirmed", draft))
    assert reviewed["verdict"] == "revised"
    assert reviewed["final_text"] == "The decision stands."
    assert any("E9999" in str(issue) for issue in reviewed["issues"])


def test_a_decision_that_contradicts_eligibility_is_marked_revised() -> None:
    draft = "Denied."
    evidence = Evidence()
    evidence.add(
        "check_request_eligibility",
        {"employee_id": "E1001", "item": "monitor"},
        {"ok": True, "eligible": True, "reason_code": None, "rule": "room"},
    )
    reviewed = reflect(draft, "deny", evidence, _judge("confirmed", draft))
    assert reviewed["verdict"] == "revised"
    assert reviewed["final_text"] == draft
    assert any(
        "does not match eligible true" in str(issue) for issue in reviewed["issues"]
    )


def test_faithful_draft_is_confirmed() -> None:
    draft = "Approved. standard may hold 1 monitor."
    llm = _judge("confirmed", draft)
    reviewed = reflect(draft, "approve", _evidence(), llm)
    assert reviewed["verdict"] == "confirmed"
    assert reviewed["final_text"] == draft
    assert reviewed["issues"] == []
    prompt = str(llm.sent[0][0]["content"])
    assert "You are the judge" in prompt
    assert "standard may hold 1 monitor" in prompt
