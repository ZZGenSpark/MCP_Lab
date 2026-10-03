"""Parser cases: a valid decision and malformed text."""

from __future__ import annotations

from equipment_host.parser import Final, Malformed, parse_decision


def test_decision_json() -> None:
    parsed = parse_decision(
        "The policy allows it.\n"
        '{"decision": "approve", "reason_code": null, "text": "Approved."}'
    )
    assert parsed == Final(
        decision="approve",
        reason_code=None,
        text="Approved.",
        thought="The policy allows it.",
    )


def test_fenced_decision_json() -> None:
    parsed = parse_decision(
        '```json\n{"decision": "deny", "reason_code": "UNKNOWN_ITEM", "text": "No."}\n```'
    )
    assert isinstance(parsed, Final)
    assert parsed.decision == "deny"
    assert parsed.reason_code == "UNKNOWN_ITEM"


def test_text_after_the_json_is_ignored() -> None:
    parsed = parse_decision(
        '{"decision": "deny", "reason_code": "UNKNOWN_ITEM", "text": "No."}\n'
        "Let me know if you need anything else."
    )
    assert isinstance(parsed, Final)
    assert parsed.decision == "deny"
    assert parsed.text == "No."


def test_think_block_before_the_json_is_dropped() -> None:
    parsed = parse_decision(
        "<think>\nI should approve.\n</think>\n"
        '{"decision": "approve", "reason_code": null, "text": "Approved."}'
    )
    assert isinstance(parsed, Final)
    assert parsed.decision == "approve"


def test_malformed_decision_is_reported() -> None:
    missing = parse_decision("I should decide, but this is not JSON.")
    assert isinstance(missing, Malformed)
    assert missing.message == "missing decision JSON"
    bad_json = parse_decision('{"decision":')
    assert isinstance(bad_json, Malformed)
    assert bad_json.message == "decision JSON is invalid"
