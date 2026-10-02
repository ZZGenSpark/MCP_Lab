"""Unit tests for get_policy_limits. Limits are the requirements table."""

from __future__ import annotations

import pytest
from equipment_server.tools import get_policy_limits

Limit = tuple[int, int | None]

# Role, item, max quantity, refresh years. Refresh is None when quantity is 0.
EXPECTED: dict[str, dict[str, Limit]] = {
    "standard": {
        "monitor": (1, 3),
        "laptop": (1, 4),
        "keyboard": (1, 2),
        "mouse": (1, 2),
        "dock": (1, 2),
        "headset": (1, 2),
    },
    "manager": {
        "monitor": (2, 3),
        "laptop": (1, 2),
        "keyboard": (1, 2),
        "mouse": (1, 2),
        "dock": (1, 2),
        "headset": (1, 2),
    },
    "contractor": {
        "monitor": (0, None),
        "laptop": (0, None),
        "keyboard": (1, 2),
        "mouse": (1, 2),
        "dock": (1, 2),
        "headset": (1, 2),
    },
    "intern": {
        "monitor": (0, None),
        "laptop": (0, None),
        "keyboard": (1, 2),
        "mouse": (1, 2),
        "dock": (1, 2),
        "headset": (1, 2),
    },
}


def _rows(role: str) -> list[dict[str, object]]:
    return [
        {"item": item, "max_quantity": quantity, "refresh_years": years}
        for item, (quantity, years) in EXPECTED[role].items()
    ]


@pytest.mark.parametrize("role", list(EXPECTED))
def test_each_role_exact_limits(role: str) -> None:
    result = get_policy_limits(role)
    assert result["ok"] is True
    assert result["role"] == role
    assert result["limits"] == _rows(role)
    assert result["eligible_items"] == [
        row["item"] for row in _rows(role) if row["max_quantity"] != 0
    ]


def test_mixed_case_and_whitespace_normalize_to_the_role() -> None:
    result = get_policy_limits("  MaNaGeR\t")
    assert result["ok"] is True
    assert result["role"] == "manager"
    assert result["limits"] == _rows("manager")
    assert result["limits"][0] == {
        "item": "monitor",
        "max_quantity": 2,
        "refresh_years": 3,
    }
    assert result["limits"][1]["refresh_years"] == 2


def test_unknown_role() -> None:
    result = get_policy_limits("boss")
    assert result == {
        "ok": False,
        "error": {
            "code": "UNKNOWN_ROLE",
            "message": "Unknown role 'boss'",
            "field": "role",
            "retryable": False,
            "hint": "Use one of: standard, manager, contractor, intern",
        },
    }


@pytest.mark.parametrize("role", ["", "   ", None])
def test_empty_input(role: object) -> None:
    result = get_policy_limits(role)
    assert result["ok"] is False
    error = result["error"]
    assert error["code"] == "INVALID_ARGUMENT"
    assert error["field"] == "role"
    assert error["retryable"] is True
    assert error["message"] == "role must be a non-empty string"
    assert error["hint"] == "Use one of: standard, manager, contractor, intern"
