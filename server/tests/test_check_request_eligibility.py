"""Unit tests for check_request_eligibility. Dates use an injected today."""

from __future__ import annotations

from datetime import date

import pytest
from equipment_server.loaders import Directory, Employee, EquipmentRecord
from equipment_server.tools import check_request_eligibility

TODAY = date(2026, 1, 1)
CATALOG_HINT = "Requestable items: monitor, laptop, keyboard, mouse, dock, headset"


def test_eligible_when_the_cap_has_room() -> None:
    result = check_request_eligibility("E1001", " monitor ", today=TODAY)
    assert result == {
        "ok": True,
        "employee_id": "E1001",
        "item": "monitor",
        "eligible": True,
        "reason_code": None,
        "rule": "standard may hold 1 monitor; refresh 3 years; 0 inside the window",
    }


def test_contractor_peripheral_is_eligible() -> None:
    result = check_request_eligibility("E1002", "keyboard", today=TODAY)
    assert result["ok"] is True
    assert result["eligible"] is True
    assert result["reason_code"] is None
    assert result["rule"] == (
        "contractor may hold 1 keyboard; refresh 2 years; 0 inside the window"
    )


def test_ineligible_role_item() -> None:
    result = check_request_eligibility("E1002", " Laptop ", today=TODAY)
    assert result == {
        "ok": True,
        "employee_id": "E1002",
        "item": "laptop",
        "eligible": False,
        "reason_code": "ROLE_NOT_ELIGIBLE",
        "rule": "contractor cannot request a laptop",
    }


def test_inside_window_reaches_the_cap() -> None:
    result = check_request_eligibility("E1006", "monitor", today=TODAY)
    assert result == {
        "ok": True,
        "employee_id": "E1006",
        "item": "monitor",
        "eligible": False,
        "reason_code": "LIMIT_REACHED",
        "rule": "standard may hold 1 monitor; refresh 3 years; 1 inside the window",
    }


def test_near_boundary_laptop_is_unclear() -> None:
    result = check_request_eligibility("E1003", "laptop", today=TODAY)
    assert result == {
        "ok": True,
        "employee_id": "E1003",
        "item": "laptop",
        "eligible": "unclear",
        "reason_code": "WITHIN_WINDOW_WITH_REASON",
        "rule": "standard laptop issued 2022-02-06 has 36 days left in the 4-year window",
    }


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (
            date(2027, 5, 31),
            {
                "ok": True,
                "employee_id": "E1006",
                "item": "monitor",
                "eligible": "unclear",
                "reason_code": "WITHIN_WINDOW_WITH_REASON",
                "rule": (
                    "standard monitor issued 2024-06-01 has 1 day left "
                    "in the 3-year window"
                ),
            },
        ),
        (
            date(2027, 6, 1),
            {
                "ok": True,
                "employee_id": "E1006",
                "item": "monitor",
                "eligible": True,
                "reason_code": None,
                "rule": (
                    "standard may hold 1 monitor; refresh 3 years; 0 inside the window"
                ),
            },
        ),
        (
            date(2027, 6, 2),
            {
                "ok": True,
                "employee_id": "E1006",
                "item": "monitor",
                "eligible": True,
                "reason_code": None,
                "rule": (
                    "standard may hold 1 monitor; refresh 3 years; 0 inside the window"
                ),
            },
        ),
    ],
)
def test_refresh_boundary_and_one_day_either_side(
    today: date, expected: dict[str, object]
) -> None:
    assert check_request_eligibility("E1006", "monitor", today=today) == expected


def test_unknown_employee() -> None:
    result = check_request_eligibility("E9999", "monitor", today=TODAY)
    assert result == {
        "ok": False,
        "error": {
            "code": "EMPLOYEE_NOT_FOUND",
            "message": "No employee with id E9999",
            "field": "employee_id",
            "retryable": False,
            "hint": "Check the id format E#### or ask the requester to confirm.",
        },
    }


def test_unknown_item() -> None:
    result = check_request_eligibility("E1001", "standing desk", today=TODAY)
    assert result == {
        "ok": False,
        "error": {
            "code": "UNKNOWN_ITEM",
            "message": "Unknown item 'standing desk'",
            "field": "item",
            "retryable": False,
            "hint": CATALOG_HINT,
        },
    }


def test_employee_is_checked_before_the_item() -> None:
    result = check_request_eligibility("E9999", "standing desk", today=TODAY)
    assert result["ok"] is False
    assert result["error"]["code"] == "EMPLOYEE_NOT_FOUND"


def test_malformed_id_is_rejected_before_the_item() -> None:
    result = check_request_eligibility("abc", None, today=TODAY)
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert result["error"]["field"] == "employee_id"


def test_missing_issue_date_is_data_conflict() -> None:
    directory = Directory(
        (
            Employee(
                employee_id="E1001",
                role="standard",
                start_date="2020-01-15",
                equipment=(EquipmentRecord(item="monitor", issued_on=None),),
            ),
        )
    )
    result = check_request_eligibility(
        "E1001", "monitor", today=TODAY, directory=directory
    )
    assert result == {
        "ok": True,
        "employee_id": "E1001",
        "item": "monitor",
        "eligible": "unclear",
        "reason_code": "DATA_CONFLICT",
        "rule": "monitor on file has no usable issued_on",
    }


def test_held_forbidden_item_is_data_conflict_before_role_denial() -> None:
    result = check_request_eligibility("E1005", "laptop", today=TODAY)
    assert result == {
        "ok": True,
        "employee_id": "E1005",
        "item": "laptop",
        "eligible": "unclear",
        "reason_code": "DATA_CONFLICT",
        "rule": "contractor already holds a laptop, which that role cannot have",
    }


def test_probation_under_90_days() -> None:
    result = check_request_eligibility("E1004", "monitor")
    assert result == {
        "ok": True,
        "employee_id": "E1004",
        "item": "monitor",
        "eligible": "unclear",
        "reason_code": "TENURE_UNDER_90_DAYS",
        "rule": "tenure is 89 days, under the 90-day probation",
    }


def test_probation_completes_on_day_90() -> None:
    result = check_request_eligibility("E1004", "monitor", today=date(2026, 1, 2))
    assert result["eligible"] is True
    assert result["reason_code"] is None


def test_cap_is_checked_before_probation() -> None:
    directory = Directory(
        (
            Employee(
                employee_id="E1004",
                role="standard",
                start_date="2025-10-04",
                equipment=(EquipmentRecord(item="monitor", issued_on="2024-06-01"),),
            ),
        )
    )
    result = check_request_eligibility(
        "E1004", "monitor", today=TODAY, directory=directory
    )
    assert result["eligible"] is False
    assert result["reason_code"] == "LIMIT_REACHED"


# --- hardware failure reason (cap reached, window still open) ---------------


def test_hardware_failure_reason_escalates_instead_of_denying() -> None:
    result = check_request_eligibility(
        "E1006", "monitor", "My monitor is broken.", today=TODAY
    )
    assert result == {
        "ok": True,
        "employee_id": "E1006",
        "item": "monitor",
        "eligible": "unclear",
        "reason_code": "WITHIN_WINDOW_WITH_REASON",
        "rule": (
            "standard monitor issued 2024-06-01 has 516 days left in the "
            "3-year window; the reason reports a hardware failure ('broken')"
        ),
    }


@pytest.mark.parametrize(
    "reason",
    [
        "it will not turn on",
        "Screen DAMAGED on arrival",
        "The monitor won't turn on",
        "The monitor won\u2019t turn on",
        "The panel is dead.",
        "It keeps failing every hour",
    ],
)
def test_each_hardware_failure_phrase_escalates(reason: str) -> None:
    result = check_request_eligibility("E1006", "monitor", reason, today=TODAY)
    assert result["eligible"] == "unclear"
    assert result["reason_code"] == "WITHIN_WINDOW_WITH_REASON"
    assert "hardware failure" in result["rule"]


def test_a_reason_without_a_failure_is_still_limit_reached() -> None:
    result = check_request_eligibility(
        "E1006", "monitor", "I would like a second screen.", today=TODAY
    )
    assert result["eligible"] is False
    assert result["reason_code"] == "LIMIT_REACHED"


def test_hardware_matching_is_a_substring_test() -> None:
    # docs/requirements.md defines a substring match, so "deadline" holds "dead".
    # The only effect is a human review, never a wrong approval or denial.
    result = check_request_eligibility(
        "E1006", "monitor", "I need one before my deadline.", today=TODAY
    )
    assert result["reason_code"] == "WITHIN_WINDOW_WITH_REASON"


def test_hardware_failure_does_not_change_an_approval() -> None:
    result = check_request_eligibility(
        "E1001", "monitor", "My old monitor is broken.", today=TODAY
    )
    assert result["eligible"] is True
    assert result["reason_code"] is None


def test_hardware_failure_does_not_change_a_role_denial() -> None:
    result = check_request_eligibility(
        "E1002", "laptop", "The laptop is broken beyond repair.", today=TODAY
    )
    assert result["eligible"] is False
    assert result["reason_code"] == "ROLE_NOT_ELIGIBLE"


def test_hardware_failure_does_not_change_a_data_conflict() -> None:
    result = check_request_eligibility(
        "E1005", "laptop", "My laptop is broken.", today=TODAY
    )
    assert result["eligible"] == "unclear"
    assert result["reason_code"] == "DATA_CONFLICT"


def test_hardware_failure_after_the_window_just_approves() -> None:
    result = check_request_eligibility(
        "E1006", "monitor", "My monitor is broken.", today=date(2027, 6, 1)
    )
    assert result["eligible"] is True


# --- vague request (row 2 of the decision table) ----------------------------


@pytest.mark.parametrize("item", ["", "   ", None])
def test_no_item_named_is_a_vague_request(item: object) -> None:
    result = check_request_eligibility("E1001", item, "Help.", today=TODAY)
    assert result == {
        "ok": True,
        "employee_id": "E1001",
        "item": None,
        "eligible": "unclear",
        "reason_code": "VAGUE_REQUEST",
        "rule": "the request does not name an item",
    }


def test_no_item_is_vague_even_with_a_good_reason() -> None:
    result = check_request_eligibility(
        "E1001", "", "I need something for my desk.", today=TODAY
    )
    assert result["reason_code"] == "VAGUE_REQUEST"


def test_short_reason_is_a_vague_request() -> None:
    result = check_request_eligibility("E1001", "monitor", "need", today=TODAY)
    assert result == {
        "ok": True,
        "employee_id": "E1001",
        "item": "monitor",
        "eligible": "unclear",
        "reason_code": "VAGUE_REQUEST",
        "rule": "the reason is under 10 characters",
    }


@pytest.mark.parametrize("reason", ["", "   "])
def test_empty_reason_is_a_vague_request(reason: str) -> None:
    result = check_request_eligibility("E1001", "monitor", reason, today=TODAY)
    assert result["reason_code"] == "VAGUE_REQUEST"
    assert result["rule"] == "the reason is empty"


def test_ten_characters_is_enough_and_nine_is_not() -> None:
    enough = check_request_eligibility("E1001", "monitor", "1234567890", today=TODAY)
    short = check_request_eligibility("E1001", "monitor", "123456789", today=TODAY)
    assert enough["eligible"] is True
    assert short["reason_code"] == "VAGUE_REQUEST"


def test_an_escalation_code_is_not_a_vague_reason() -> None:
    result = check_request_eligibility("E1001", "monitor", "DATA_CONFLICT", today=TODAY)
    assert result["eligible"] is True


def test_an_omitted_reason_is_not_judged() -> None:
    explicit = check_request_eligibility("E1001", "monitor", None, today=TODAY)
    omitted = check_request_eligibility("E1001", "monitor", today=TODAY)
    assert explicit == omitted
    assert omitted["eligible"] is True


def test_unknown_employee_comes_before_the_vague_check() -> None:
    result = check_request_eligibility("E9999", "", "Help.", today=TODAY)
    assert result["ok"] is False
    assert result["error"]["code"] == "EMPLOYEE_NOT_FOUND"


def test_vague_request_comes_before_the_unknown_item_check() -> None:
    result = check_request_eligibility("E1001", "Standing Desk", "Help.", today=TODAY)
    assert result["reason_code"] == "VAGUE_REQUEST"
    assert result["item"] == "standing desk"


def test_unknown_item_with_a_good_reason_is_still_denied() -> None:
    result = check_request_eligibility(
        "E1001", "standing desk", "I need a standing desk.", today=TODAY
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "UNKNOWN_ITEM"


def test_vague_request_comes_before_the_data_conflict_check() -> None:
    result = check_request_eligibility("E1005", "laptop", "Help.", today=TODAY)
    assert result["reason_code"] == "VAGUE_REQUEST"


def test_a_non_string_item_is_an_invalid_argument() -> None:
    result = check_request_eligibility("E1001", 5, "I need a monitor.", today=TODAY)
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert result["error"]["field"] == "item"


# --- other roles and calendar edges -----------------------------------------


def _staff(role: str, *units: tuple[str, str]) -> Directory:
    return Directory(
        (
            Employee(
                employee_id="E2001",
                role=role,
                start_date="2020-01-15",
                equipment=tuple(
                    EquipmentRecord(item=item, issued_on=issued)
                    for item, issued in units
                ),
            ),
        )
    )


def test_manager_may_hold_a_second_monitor() -> None:
    directory = _staff("manager", ("monitor", "2024-06-01"))
    result = check_request_eligibility(
        "E2001", "monitor", today=TODAY, directory=directory
    )
    assert result["eligible"] is True
    assert result["rule"] == (
        "manager may hold 2 monitor; refresh 3 years; 1 inside the window"
    )


def test_manager_with_two_monitors_inside_the_window_is_at_the_limit() -> None:
    directory = _staff("manager", ("monitor", "2024-06-01"), ("monitor", "2024-07-01"))
    result = check_request_eligibility(
        "E2001", "monitor", today=TODAY, directory=directory
    )
    assert result["eligible"] is False
    assert result["reason_code"] == "LIMIT_REACHED"
    assert result["rule"] == (
        "manager may hold 2 monitor; refresh 3 years; 2 inside the window"
    )


def test_a_monitor_outside_the_window_does_not_count_toward_the_cap() -> None:
    directory = _staff("manager", ("monitor", "2022-12-31"), ("monitor", "2024-06-01"))
    result = check_request_eligibility(
        "E2001", "monitor", today=TODAY, directory=directory
    )
    assert result["eligible"] is True
    assert "1 inside the window" in result["rule"]


def test_manager_laptop_refreshes_after_two_years_but_standard_waits_four() -> None:
    manager = _staff("manager", ("laptop", "2024-01-01"))
    standard = _staff("standard", ("laptop", "2024-01-01"))
    refreshed = check_request_eligibility(
        "E2001", "laptop", today=TODAY, directory=manager
    )
    waiting = check_request_eligibility(
        "E2001", "laptop", today=TODAY, directory=standard
    )
    assert refreshed["eligible"] is True
    assert waiting["eligible"] is False
    assert waiting["reason_code"] == "LIMIT_REACHED"


def test_intern_cannot_request_a_laptop_but_can_request_a_keyboard() -> None:
    directory = _staff("intern")
    laptop = check_request_eligibility(
        "E2001", "laptop", today=TODAY, directory=directory
    )
    keyboard = check_request_eligibility(
        "E2001", "keyboard", today=TODAY, directory=directory
    )
    assert laptop["reason_code"] == "ROLE_NOT_ELIGIBLE"
    assert laptop["rule"] == "intern cannot request a laptop"
    assert keyboard["eligible"] is True


def test_leap_day_anniversary_falls_back_to_the_28th() -> None:
    directory = _staff("standard", ("keyboard", "2024-02-29"))
    inside = check_request_eligibility(
        "E2001", "keyboard", today=date(2026, 2, 27), directory=directory
    )
    on_the_day = check_request_eligibility(
        "E2001", "keyboard", today=date(2026, 2, 28), directory=directory
    )
    assert inside["eligible"] == "unclear"
    assert inside["rule"] == (
        "standard keyboard issued 2024-02-29 has 1 day left in the 2-year window"
    )
    assert on_the_day["eligible"] is True
