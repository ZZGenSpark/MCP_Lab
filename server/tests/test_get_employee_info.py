"""Unit tests for get_employee_info. Tenure uses an injected today."""

from __future__ import annotations

from datetime import date

import pytest
from equipment_server.tools import get_employee_info

TODAY = date(2026, 1, 1)


def test_happy_path_includes_role_tenure_and_equipment_dates() -> None:
    result = get_employee_info("E1003", today=TODAY)
    assert result == {
        "ok": True,
        "employee_id": "E1003",
        "role": "standard",
        "start_date": "2019-03-01",
        "tenure_days": 2498,
        "equipment": [{"item": "laptop", "issued_on": "2022-02-06"}],
    }


def test_empty_equipment_list() -> None:
    result = get_employee_info(" E1001 ", today=TODAY)
    assert result == {
        "ok": True,
        "employee_id": "E1001",
        "role": "standard",
        "start_date": "2020-01-15",
        "tenure_days": 2178,
        "equipment": [],
    }


def test_tenure_follows_the_injected_date() -> None:
    day_after = get_employee_info("E1004", today=date(2026, 1, 2))
    assert day_after["tenure_days"] == 90
    on_requirements_day = get_employee_info("E1004")
    assert on_requirements_day["tenure_days"] == 89


def test_unknown_id() -> None:
    result = get_employee_info("E9999", today=TODAY)
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


@pytest.mark.parametrize(
    ("employee_id", "message"),
    [
        ("abc", "employee_id 'abc' does not match E####"),
        (None, "employee_id must be a string like E1001"),
        ("e0001", "employee_id 'e0001' does not match E####"),
    ],
)
def test_malformed_ids(employee_id: object, message: str) -> None:
    result = get_employee_info(employee_id, today=TODAY)
    assert result == {
        "ok": False,
        "error": {
            "code": "INVALID_ARGUMENT",
            "message": message,
            "field": "employee_id",
            "retryable": True,
            "hint": "Use an employee id like E1001: uppercase E and four digits.",
        },
    }
