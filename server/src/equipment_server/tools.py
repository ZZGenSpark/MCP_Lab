"""Plain tool functions. MCP registration lives in server.py."""

from __future__ import annotations

from datetime import date
from typing import Any

from equipment_server.loaders import (
    Directory,
    Employee,
    EquipmentRecord,
    ItemLimit,
    PolicyData,
    load_employees,
    load_policies,
)
from equipment_server.validation import (
    policy_roles,
    validate_employee_id,
    validate_item,
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


def check_request_eligibility(
    employee_id: object,
    item: object,
    *,
    today: date | None = None,
    directory: Directory | None = None,
    policies: PolicyData | None = None,
) -> dict[str, Any]:
    """Report whether one catalog item is inside policy for this employee.

    Checks stop at the first match, in decision-table order: the employee
    exists, the item is in the catalog, a unit of that item has a usable
    issue date, the employee does not already hold an item the role cannot
    have, the role's quantity is above zero, the refresh window still has
    room, then probation. `eligible` is true, false, or "unclear".
    """
    directory = load_employees() if directory is None else directory
    policies = load_policies() if policies is None else policies
    today = LAB_TODAY if today is None else today

    employee = validate_employee_id(employee_id, directory)
    if isinstance(employee, dict):
        return employee
    normalized = validate_item(item, policies.catalog)
    if isinstance(normalized, dict):
        return normalized

    missing_date = _missing_issue_date(employee, normalized)
    if missing_date is not None:
        return _decision(
            employee.employee_id,
            normalized,
            "unclear",
            "DATA_CONFLICT",
            f"{normalized} on file has no usable issued_on",
        )
    forbidden = _forbidden_holding(employee, policies)
    if forbidden is not None:
        return _decision(
            employee.employee_id,
            normalized,
            "unclear",
            "DATA_CONFLICT",
            (
                f"{employee.role} already holds a {forbidden}, "
                "which that role cannot have"
            ),
        )

    limit = policies.limit_for(employee.role, normalized)
    if limit is None or limit.max_quantity == 0 or limit.refresh_years is None:
        return _decision(
            employee.employee_id,
            normalized,
            False,
            "ROLE_NOT_ELIGIBLE",
            f"{employee.role} cannot request a {normalized}",
        )

    held = _units_inside_window(employee, normalized, limit, today, policies)
    if len(held) >= limit.max_quantity:
        nearest = min(held, key=lambda unit: unit.days_left)
        if nearest.near:
            return _decision(
                employee.employee_id,
                normalized,
                "unclear",
                "WITHIN_WINDOW_WITH_REASON",
                (
                    f"{employee.role} {normalized} issued {nearest.issued_on} "
                    f"has {_day_span(nearest.days_left)} left in the "
                    f"{limit.refresh_years}-year window"
                ),
            )
        return _decision(
            employee.employee_id,
            normalized,
            False,
            "LIMIT_REACHED",
            _quantity_rule(employee.role, normalized, limit, len(held)),
        )

    tenure_days = (today - date.fromisoformat(employee.start_date)).days
    if tenure_days < policies.probation_days:
        return _decision(
            employee.employee_id,
            normalized,
            "unclear",
            "TENURE_UNDER_90_DAYS",
            (
                f"tenure is {tenure_days} days, under the "
                f"{policies.probation_days}-day probation"
            ),
        )
    return _decision(
        employee.employee_id,
        normalized,
        True,
        None,
        _quantity_rule(employee.role, normalized, limit, len(held)),
    )


def _decision(
    employee_id: str,
    item: str,
    eligible: bool | str,
    reason_code: str | None,
    rule: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "employee_id": employee_id,
        "item": item,
        "eligible": eligible,
        "reason_code": reason_code,
        "rule": rule,
    }


def _quantity_rule(role: str, item: str, limit: ItemLimit, inside: int) -> str:
    return (
        f"{role} may hold {limit.max_quantity} {item}; "
        f"refresh {limit.refresh_years} years; {inside} inside the window"
    )


def _day_span(days: int) -> str:
    unit = "day" if days == 1 else "days"
    return f"{days} {unit}"


def _missing_issue_date(employee: Employee, item: str) -> EquipmentRecord | None:
    for unit in employee.equipment:
        if unit.item == item and _issued_on(unit.issued_on) is None:
            return unit
    return None


def _forbidden_holding(employee: Employee, policies: PolicyData) -> str | None:
    for unit in employee.equipment:
        limit = policies.limit_for(employee.role, unit.item)
        if limit is not None and limit.max_quantity == 0:
            return unit.item
    return None


def _units_inside_window(
    employee: Employee,
    item: str,
    limit: ItemLimit,
    today: date,
    policies: PolicyData,
) -> list[_HeldUnit]:
    years = limit.refresh_years
    if years is None:
        return []
    allowance = round(years * 365.25 * policies.near_boundary_fraction)
    held: list[_HeldUnit] = []
    for unit in employee.equipment:
        if unit.item != item:
            continue
        issued = _issued_on(unit.issued_on)
        if issued is None:
            continue
        anniversary = _add_years(issued, years)
        if today >= anniversary:
            continue
        days_left = (anniversary - today).days
        held.append(
            _HeldUnit(
                issued_on=issued.isoformat(),
                days_left=days_left,
                near=days_left <= allowance,
            )
        )
    return held


class _HeldUnit:
    def __init__(self, issued_on: str, days_left: int, near: bool) -> None:
        self.issued_on = issued_on
        self.days_left = days_left
        self.near = near


def _issued_on(value: str | None) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)
