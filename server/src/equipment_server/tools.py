"""Plain tool functions. MCP registration lives in server.py."""

from __future__ import annotations

from datetime import date
from typing import Any

from equipment_server.loaders import (
    Directory,
    PolicyData,
    load_employees,
    load_policies,
)
from equipment_server.validation import (
    policy_roles,
    validate_employee_id,
    validate_role,
)

# Requirements scenarios are judged on this date. Tools use it when today is omitted.
LAB_TODAY = date(2026, 1, 1)


def get_employee_info(
    employee_id: object,
    *,
    today: date | None = None,
    directory: Directory | None = None,
) -> dict[str, Any]:
    """Return role, tenure, and equipment on file for one employee.

    The id must match E#### and exist in the directory. Tenure is the number
    of days from start_date to today. A rejected id returns a tool error.
    """
    directory = load_employees() if directory is None else directory
    today = LAB_TODAY if today is None else today
    employee = validate_employee_id(employee_id, directory)
    if isinstance(employee, dict):
        return employee
    return {
        "ok": True,
        "employee_id": employee.employee_id,
        "role": employee.role,
        "start_date": employee.start_date,
        "tenure_days": (today - date.fromisoformat(employee.start_date)).days,
        "equipment": [
            {"item": unit.item, "issued_on": unit.issued_on}
            for unit in employee.equipment
        ],
    }


def get_policy_limits(
    role: object, *, policies: PolicyData | None = None
) -> dict[str, Any]:
    """Return one role's item limits and the items that role may request.

    The role is trimmed and lowercased. An unknown or empty role returns a
    structured tool error and does not read any other policy fields.
    """
    policies = load_policies() if policies is None else policies
    normalized = validate_role(role, policy_roles(policies))
    if isinstance(normalized, dict):
        return normalized
    limits = [
        {
            "item": limit.item,
            "max_quantity": limit.max_quantity,
            "refresh_years": limit.refresh_years,
        }
        for limit in policies.limits
        if limit.role == normalized
    ]
    return {
        "ok": True,
        "role": normalized,
        "eligible_items": [row["item"] for row in limits if row["max_quantity"] > 0],
        "limits": limits,
    }
