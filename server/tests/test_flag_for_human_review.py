"""flag_for_human_review writes a ticket only after every check passes."""

from __future__ import annotations

import pytest
from equipment_server.store import FlagStore
from equipment_server.tools import flag_for_human_review

REQUEST = "I need a monitor for my desk."
REASON = "The desk has no display for daily work."


def _flag(
    employee_id: object,
    request: object,
    reason: object,
    store: FlagStore,
) -> dict[str, object]:
    return flag_for_human_review(employee_id, request, reason, store=store)


def test_success_creates_rev_0001() -> None:
    store = FlagStore()
    result = _flag("E1001", REQUEST, REASON, store)
    assert result == {
        "ok": True,
        "ticket_id": "REV-0001",
        "status": "pending_review",
    }
    assert len(store.records()) == 1
    record = store.records()[0]
    assert record.employee_id == "E1001"
    assert record.item == "monitor"
    assert record.request == REQUEST
    assert record.reason == REASON
    assert record.status == "pending_review"


def test_ticket_ids_increment() -> None:
    store = FlagStore()
    first = _flag("E1001", REQUEST, REASON, store)
    second = _flag(
        "E1001",
        "I need a keyboard.",
        "The current keyboard is missing keys.",
        store,
    )
    assert first["ticket_id"] == "REV-0001"
    assert second["ticket_id"] == "REV-0002"
    assert len(store.records()) == 2


@pytest.mark.parametrize(
    ("employee_id", "request_text", "reason", "code"),
    [
        ("E9999", REQUEST, REASON, "EMPLOYEE_NOT_FOUND"),
        ("abc", REQUEST, REASON, "INVALID_ARGUMENT"),
        ("E1001", "   ", REASON, "INVALID_ARGUMENT"),
        ("E1001", "I need a standing desk", REASON, "UNKNOWN_ITEM"),
        ("E1001", REQUEST, "short", "INVALID_ARGUMENT"),
    ],
)
def test_validation_failure_leaves_the_store_empty(
    employee_id: object, request_text: object, reason: object, code: str
) -> None:
    store = FlagStore()
    result = _flag(employee_id, request_text, reason, store)
    assert result["ok"] is False
    assert result["error"]["code"] == code
    assert store.records() == ()


def test_duplicate_flag_does_not_create_a_second_ticket() -> None:
    store = FlagStore()
    first = _flag("E1001", REQUEST, REASON, store)
    second = _flag("E1001", "Please review a monitor request.", REASON, store)
    assert first["ticket_id"] == "REV-0001"
    assert second["ok"] is False
    assert second["error"]["code"] == "DUPLICATE_FLAG"
    assert len(store.records()) == 1


def test_known_reason_code_is_accepted() -> None:
    store = FlagStore()
    result = _flag(
        "E1003", "Please review the laptop.", "WITHIN_WINDOW_WITH_REASON", store
    )
    assert result["ok"] is True
    assert store.records()[0].reason == "WITHIN_WINDOW_WITH_REASON"
