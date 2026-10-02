"""Parser cases: a valid action, a valid final, and malformed text."""

from __future__ import annotations

from equipment_host.parser import Action, Final, Malformed, parse_reply


def test_action_with_json() -> None:
    parsed = parse_reply(
        'Thought: Look up the employee.\nAction: get_employee_info {"employee_id": "E1001"}'
    )
    assert parsed == Action(
        name="get_employee_info",
        arguments={"employee_id": "E1001"},
        thought="Look up the employee.",
    )


def test_final_decision() -> None:
    parsed = parse_reply(
        "Thought: The policy allows it.\n"
        'Final: {"decision": "approve", "reason_code": null, "text": "Approved."}'
    )
    assert parsed == Final(
        decision="approve",
        reason_code=None,
        text="Approved.",
        thought="The policy allows it.",
    )


def test_malformed_then_the_shape_is_reported() -> None:
    missing = parse_reply("Thought: I should decide.\nNo action here.")
    assert isinstance(missing, Malformed)
    assert missing.message == "missing Action or Final"
    bad_json = parse_reply("Action: get_employee_info {")
    assert isinstance(bad_json, Malformed)
