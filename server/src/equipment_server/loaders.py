"""Load mock employees and policy limits from the package data files."""

# JSON schema failures are ValueError so callers have one error type to catch.
# ruff: noqa: TRY004

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
EMPLOYEE_ID = re.compile(r"^E\d{4}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class EquipmentRecord:
    item: str
    issued_on: str | None


@dataclass(frozen=True)
class Employee:
    employee_id: str
    role: str
    start_date: str
    equipment: tuple[EquipmentRecord, ...]


@dataclass(frozen=True)
class Directory:
    employees: tuple[Employee, ...]

    def by_id(self) -> dict[str, Employee]:
        return {employee.employee_id: employee for employee in self.employees}


@dataclass(frozen=True)
class ItemLimit:
    role: str
    item: str
    max_quantity: int
    refresh_years: int | None


@dataclass(frozen=True)
class PolicyData:
    probation_days: int
    near_boundary_fraction: float
    catalog: tuple[str, ...]
    hardware_failure_terms: tuple[str, ...]
    limits: tuple[ItemLimit, ...]

    def limit_for(self, role: str, item: str) -> ItemLimit | None:
        for limit in self.limits:
            if limit.role == role and limit.item == item:
                return limit
        return None


def load_employees(path: Path | None = None) -> Directory:
    """Load the employee directory. `issued_on` may be null."""
    payload = _read_json(path or DATA_DIR / "employees.json")
    if not isinstance(payload, list):
        raise ValueError("employees.json must be a list of employee records")
    employees = tuple(_employee(record) for record in payload)
    ids = [employee.employee_id for employee in employees]
    if len(ids) != len(set(ids)):
        raise ValueError("employee_id values must be unique")
    return Directory(employees)


def load_policies(path: Path | None = None) -> PolicyData:
    """Load catalog, probation, and per-role item limits."""
    payload = _read_json(path or DATA_DIR / "policies.json")
    if not isinstance(payload, dict):
        raise ValueError("policies.json must be an object")
    catalog = tuple(_name_list(payload.get("catalog"), "catalog"))
    terms = tuple(
        _name_list(payload.get("hardware_failure_terms"), "hardware_failure_terms")
    )
    probation_days = _non_negative_int(payload.get("probation_days"), "probation_days")
    fraction = payload.get("near_boundary_fraction")
    if isinstance(fraction, bool) or not isinstance(fraction, int | float):
        raise ValueError("near_boundary_fraction must be a number")
    if not 0 < float(fraction) <= 1:
        raise ValueError("near_boundary_fraction must be in (0, 1]")
    roles = payload.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("roles must be a non-empty object")
    limits: list[ItemLimit] = []
    for role, items in roles.items():
        if not isinstance(role, str) or not role:
            raise ValueError("role names must be non-empty strings")
        if not isinstance(items, dict):
            raise ValueError(f"role {role} must map items to limits")
        if tuple(items) != catalog:
            raise ValueError(
                f"role {role} must list every catalog item in catalog order"
            )
        for item, raw in items.items():
            limits.append(_item_limit(role, item, raw))
    return PolicyData(
        probation_days=probation_days,
        near_boundary_fraction=float(fraction),
        catalog=catalog,
        hardware_failure_terms=terms,
        limits=tuple(limits),
    )


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"data file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _employee(record: object) -> Employee:
    if not isinstance(record, dict):
        raise ValueError("each employee must be an object")
    employee_id = record.get("employee_id")
    if not isinstance(employee_id, str) or EMPLOYEE_ID.fullmatch(employee_id) is None:
        raise ValueError(f"employee_id must match E####, got {employee_id!r}")
    role = record.get("role")
    if not isinstance(role, str) or not role:
        raise ValueError(f"{employee_id} role must be a non-empty string")
    start_date = record.get("start_date")
    _require_date(start_date, f"{employee_id} start_date")
    equipment = record.get("equipment")
    if not isinstance(equipment, list):
        raise ValueError(f"{employee_id} equipment must be a list")
    return Employee(
        employee_id=employee_id,
        role=role,
        start_date=start_date,
        equipment=tuple(_equipment(employee_id, unit) for unit in equipment),
    )


def _equipment(employee_id: str, unit: object) -> EquipmentRecord:
    if not isinstance(unit, dict):
        raise ValueError(f"{employee_id} equipment entries must be objects")
    item = unit.get("item")
    if not isinstance(item, str) or not item:
        raise ValueError(f"{employee_id} equipment item must be a non-empty string")
    issued_on = unit.get("issued_on")
    if issued_on is not None:
        _require_date(issued_on, f"{employee_id} {item} issued_on")
    return EquipmentRecord(item=item, issued_on=issued_on)


def _item_limit(role: str, item: str, raw: object) -> ItemLimit:
    if not isinstance(raw, dict):
        raise ValueError(f"{role}.{item} must be an object")
    max_quantity = _non_negative_int(
        raw.get("max_quantity"), f"{role}.{item} max_quantity"
    )
    refresh_years = raw.get("refresh_years")
    if max_quantity == 0:
        if refresh_years is not None:
            raise ValueError(
                f"{role}.{item} refresh_years must be null when max_quantity is 0"
            )
        return ItemLimit(role, item, 0, None)
    if (
        isinstance(refresh_years, bool)
        or not isinstance(refresh_years, int)
        or refresh_years <= 0
    ):
        raise ValueError(f"{role}.{item} refresh_years must be a positive integer")
    return ItemLimit(role, item, max_quantity, refresh_years)


def _name_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field} entries must be non-empty strings")
        names.append(item)
    if len(names) != len(set(names)):
        raise ValueError(f"{field} entries must be unique")
    return names


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be an integer >= 0")
    return value


def _require_date(value: object, field: str) -> None:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a real calendar date") from exc
