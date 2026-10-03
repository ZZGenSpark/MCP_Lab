"""Plain tool functions. MCP registration lives in server.py."""

from __future__ import annotations

from datetime import date
from typing import Any

import flowlog
from equipment_server.loaders import (
    Directory,
    Employee,
    EquipmentRecord,
    ItemLimit,
    PolicyData,
    load_employees,
    load_policies,
)
from equipment_server.store import FlagStore, flag_store
from equipment_server.validation import (
    REASON_CODES,
    REASON_MIN_LENGTH,
    policy_roles,
    validate_employee_id,
    validate_flag_request,
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
    reason: object = None,
    *,
    today: date | None = None,
    directory: Directory | None = None,
    policies: PolicyData | None = None,
) -> dict[str, Any]:
    """Report whether one catalog item is inside policy for this employee.

    Checks stop at the first match, in decision-table order: the employee
    exists, the request is not vague, the item is in the catalog, a unit of
    that item has a usable issue date, the employee does not already hold an
    item the role cannot have, the role's quantity is above zero, the refresh
    window still has room, then probation. `eligible` is true, false, or
    "unclear".

    `reason` is the requester's own words. When it is omitted the reason is
    not judged, so the two-argument call still works. A supplied reason that
    is empty or under 10 characters makes the request vague, and a reason
    that reports a hardware failure sends a request inside its window to a
    reviewer instead of denying it.
    """
    directory = load_employees() if directory is None else directory
    policies = load_policies() if policies is None else policies
    today = LAB_TODAY if today is None else today

    employee = validate_employee_id(employee_id, directory)
    if isinstance(employee, dict):
        return employee

    vague = _vague_rule(item, reason)
    if vague is not None:
        flowlog.validation(f"check request detail -> {vague}, VAGUE_REQUEST")
        return _decision(
            employee.employee_id,
            _named_item(item),
            "unclear",
            "VAGUE_REQUEST",
            vague,
        )
    flowlog.validation("check request detail -> item named, reason usable")

    normalized = validate_item(item, policies.catalog)
    if isinstance(normalized, dict):
        return normalized

    missing_date = _missing_issue_date(employee, normalized)
    if missing_date is not None:
        flowlog.validation(
            f"check issue date for {normalized} -> missing, DATA_CONFLICT"
        )
        return _decision(
            employee.employee_id,
            normalized,
            "unclear",
            "DATA_CONFLICT",
            f"{normalized} on file has no usable issued_on",
        )
    flowlog.validation(f"check issue date for {normalized} -> usable")
    forbidden = _forbidden_holding(employee, policies)
    if forbidden is not None:
        flowlog.validation(
            f"check holdings for {employee.role} -> holds {forbidden}, DATA_CONFLICT"
        )
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
    flowlog.validation(f"check holdings for {employee.role} -> allowed")

    limit = policies.limit_for(employee.role, normalized)
    if limit is None or limit.max_quantity == 0 or limit.refresh_years is None:
        flowlog.validation(
            f"check role limit for {employee.role} {normalized} -> ROLE_NOT_ELIGIBLE"
        )
        return _decision(
            employee.employee_id,
            normalized,
            False,
            "ROLE_NOT_ELIGIBLE",
            f"{employee.role} cannot request a {normalized}",
        )
    flowlog.validation(
        f"check role limit -> {employee.role} may hold {limit.max_quantity} "
        f"{normalized}; refresh {limit.refresh_years} years"
    )

    held = _units_inside_window(employee, normalized, limit, today, policies)
    if len(held) >= limit.max_quantity:
        nearest = min(held, key=lambda unit: unit.days_left)
        failure = _hardware_failure(reason, policies)
        flowlog.validation(
            "check reason for hardware failure -> "
            + ("none" if failure is None else repr(failure))
        )
        if nearest.near or failure is not None:
            flowlog.validation(
                f"check refresh window -> {_day_span(nearest.days_left)} left, "
                "WITHIN_WINDOW_WITH_REASON"
            )
            rule = (
                f"{employee.role} {normalized} issued {nearest.issued_on} "
                f"has {_day_span(nearest.days_left)} left in the "
                f"{limit.refresh_years}-year window"
            )
            if failure is not None:
                rule += f"; the reason reports a hardware failure ({failure!r})"
            return _decision(
                employee.employee_id,
                normalized,
                "unclear",
                "WITHIN_WINDOW_WITH_REASON",
                rule,
            )
        flowlog.validation(f"check refresh window -> {len(held)} inside, LIMIT_REACHED")
        return _decision(
            employee.employee_id,
            normalized,
            False,
            "LIMIT_REACHED",
            _quantity_rule(employee.role, normalized, limit, len(held)),
        )
    flowlog.validation(
        f"check refresh window -> {len(held)} inside, under the quantity limit"
    )

    tenure_days = (today - date.fromisoformat(employee.start_date)).days
    if tenure_days < policies.probation_days:
        flowlog.validation(
            f"check probation -> {tenure_days} days, under "
            f"{policies.probation_days}, TENURE_UNDER_90_DAYS"
        )
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
    flowlog.validation(
        f"check probation -> {tenure_days} days, meets "
        f"{policies.probation_days}-day probation"
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
    item: str | None,
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


def _named_item(item: object) -> str | None:
    """The item as the requester named it, or None when no item was named."""
    if isinstance(item, str) and item.strip():
        return item.strip().lower()
    return None


def _vague_rule(item: object, reason: object) -> str | None:
    """Why the request cannot be evaluated, or None when it can.

    An omitted reason (None) is not judged. A supplied reason must be an
    escalation code or at least REASON_MIN_LENGTH characters.
    """
    if _named_item(item) is None and (item is None or isinstance(item, str)):
        return "the request does not name an item"
    if reason is None:
        return None
    text = reason.strip() if isinstance(reason, str) else ""
    if text in REASON_CODES or len(text) >= REASON_MIN_LENGTH:
        return None
    if not text:
        return "the reason is empty"
    return f"the reason is under {REASON_MIN_LENGTH} characters"


def _hardware_failure(reason: object, policies: PolicyData) -> str | None:
    """The longest hardware-failure term found in the reason, or None.

    Matching is a case-insensitive substring test against the closed list in
    the policy data, as docs/requirements.md defines it.
    """
    if not isinstance(reason, str):
        return None
    lowered = reason.lower().replace("\u2019", "'")
    found = [term for term in policies.hardware_failure_terms if term in lowered]
    return max(found, key=len) if found else None


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


def flag_for_human_review(
    employee_id: object,
    request: object,
    reason: object,
    *,
    directory: Directory | None = None,
    policies: PolicyData | None = None,
    store: FlagStore | None = None,
) -> dict[str, Any]:
    """Open a review ticket after the validation chain passes.

    Checks run in order: employee, request text and catalog item, reason,
    then an open duplicate. The first failure returns a tool error and
    leaves the store unchanged. A passing request creates REV-0001 and up.
    """
    store = flag_store if store is None else store
    validated = validate_flag_request(
        employee_id,
        request,
        reason,
        directory=directory,
        policies=policies,
        store=store,
    )
    if isinstance(validated, dict):
        return validated
    record = store.create(
        validated.employee_id,
        validated.item,
        validated.request,
        validated.reason,
    )
    flowlog.validation(f"store.create -> {record.ticket_id} pending_review")
    return {"ok": True, "ticket_id": record.ticket_id, "status": "pending_review"}


def _add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)
