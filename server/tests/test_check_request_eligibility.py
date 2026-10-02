"""Unit tests for check_request_eligibility. Dates use an injected today."""

from __future__ import annotations

from datetime import date

import pytest
from equipment_server.loaders import Directory, Employee, EquipmentRecord
from equipment_server.tools import check_request_eligibility

TODAY = date(2026, 1, 1)
CATALOG_HINT = (
    "Requestable items: monitor, laptop, keyboard, mouse, dock, headset"
)


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
                    "standard may hold 1 monitor; refresh 3 years; "
                    "0 inside the window"
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
                    "standard may hold 1 monitor; refresh 3 years; "
                    "0 inside the window"
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
