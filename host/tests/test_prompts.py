"""The prompt rules that the live model needs, pinned so edits do not drop them."""

from __future__ import annotations

from equipment_host.guardrails import ESCALATE_CODES
from equipment_host.prompts import (
    ESCALATE_CODES as PROMPT_CODES,
)
from equipment_host.prompts import reflection_prompt, system_prompt

TOOLS = [
    {"name": "get_employee_info"},
    {"name": "check_request_eligibility"},
    {"name": "flag_for_human_review"},
]


def test_the_prompt_and_the_guardrails_list_the_same_escalation_codes() -> None:
    assert set(PROMPT_CODES) == set(ESCALATE_CODES)
    prompt = system_prompt(TOOLS)
    for code in ESCALATE_CODES:
        assert code in prompt


def test_system_prompt_tells_the_model_how_to_fill_each_argument() -> None:
    prompt = system_prompt(TOOLS)
    assert (
        "get_employee_info, check_request_eligibility, flag_for_human_review" in prompt
    )
    assert "pass an empty string" in prompt
    assert "copied word for word" in prompt
    assert "Arguments for flag_for_human_review" in prompt
    assert "reason_code from the eligibility result" in prompt


def test_system_prompt_asks_for_the_ticket_before_the_final_answer() -> None:
    prompt = system_prompt(TOOLS)
    assert "very next step" in prompt
    assert "until that\n  tool has returned a ticket_id" in prompt
    assert "give the reason_code, the rule" in prompt


def test_system_prompt_never_allows_reasoning_without_a_tool_call() -> None:
    assert "Never send a sentence" in system_prompt(TOOLS)


def test_reflection_prompt_carries_the_draft_and_the_observations() -> None:
    prompt = reflection_prompt("Draft text.", "approve", '[{"tool": "t"}]')
    assert "You are the judge" in prompt
    assert "Draft: Draft text." in prompt
    assert 'Observations: [{"tool": "t"}]' in prompt
    assert "Decision: approve" in prompt


def test_reflection_prompt_names_promises_and_supported_facts() -> None:
    prompt = reflection_prompt("d", "escalate", "[]")
    assert "will ship tomorrow" in prompt
    assert "ticket_id from flag_for_human_review" in prompt
    assert "message and hint inside an error result" in prompt
    assert "are supported facts" in prompt
    assert "is not a promise" in prompt


def test_reflection_prompt_shows_a_revision_and_a_clean_confirmation() -> None:
    """One example of each keeps the judge from inventing a failure."""
    prompt = reflection_prompt("d", "approve", "[]")
    assert '"verdict": "revised"}' in prompt
    assert '{"issues": [], "final_text": "Denied. A contractor' in prompt
    assert '"verdict": "confirmed"}' in prompt


def test_reflection_prompt_puts_the_verdict_after_the_corrected_text() -> None:
    """The model must write the corrected text before it commits to a verdict."""
    prompt = reflection_prompt("d", "approve", "[]")
    schema = prompt[prompt.index("write the keys in this order") :]
    assert schema.index('"issues"') < schema.index('"final_text"')
    assert schema.index('"final_text"') < schema.index('"verdict"')
    assert "exactly when final_text differs from the draft" in prompt
