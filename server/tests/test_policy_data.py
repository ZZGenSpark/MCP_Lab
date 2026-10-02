"""Mock data must match docs/requirements.md so the two cannot drift."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from equipment_server.loaders import PolicyData, load_employees, load_policies

REQUIREMENTS = Path(__file__).resolve().parents[2] / "docs" / "requirements.md"
_NO_REFRESH = {"—", "–", "-"}


def test_policies_match_requirements() -> None:
    text = REQUIREMENTS.read_text(encoding="utf-8")
    policies = load_policies()
    assert policies.probation_days == _probation_days(text)
    assert policies.near_boundary_fraction == _near_boundary_fraction(text)
    assert policies.catalog == _catalog(text)
    assert policies.hardware_failure_terms == _hardware_terms(text)
    assert _loaded_limits(policies) == _policy_table(text)


def test_employees_match_requirements_fixtures() -> None:
    directory = load_employees()
    fixtures = _employee_fixtures(REQUIREMENTS.read_text(encoding="utf-8"))
    loaded = [
        (
            employee.employee_id,
            employee.role,
            employee.start_date,
            tuple((unit.item, unit.issued_on) for unit in employee.equipment),
        )
        for employee in directory.employees
    ]
    assert loaded == fixtures
    assert "E9999" not in directory.by_id()


def test_load_employees_rejects_malformed_id(tmp_path: Path) -> None:
    path = tmp_path / "employees.json"
    path.write_text(
        json.dumps(
            [
                {
                    "employee_id": "e0001",
                    "role": "standard",
                    "start_date": "2020-01-15",
                    "equipment": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="employee_id"):
        load_employees(path)


def _loaded_limits(
    policies: PolicyData,
) -> dict[tuple[str, str], tuple[int, int | None]]:
    return {
        (limit.role, limit.item): (limit.max_quantity, limit.refresh_years)
        for limit in policies.limits
    }


def _tables(text: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [
                cell.strip().replace("`", "")
                for cell in line.strip().strip("|").split("|")
            ]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _table(text: str, header: list[str]) -> list[list[str]]:
    for table in _tables(text):
        if table[0][: len(header)] == header:
            return table[1:]
    raise AssertionError(f"table not found: {header}")


def _catalog(text: str) -> tuple[str, ...]:
    rows = _table(text, ["Item", "Group"])
    return tuple(row[0] for row in rows)


def _policy_table(text: str) -> dict[tuple[str, str], tuple[int, int | None]]:
    rows = _table(text, ["Role", "Item", "Max quantity", "Refresh (years)"])
    parsed: dict[tuple[str, str], tuple[int, int | None]] = {}
    for role, item, quantity, refresh in rows:
        years = None if refresh in _NO_REFRESH else int(refresh)
        parsed[(role, item)] = (int(quantity), years)
    return parsed


def _employee_fixtures(
    text: str,
) -> list[tuple[str, str, str, tuple[tuple[str, str], ...]]]:
    rows = _table(text, ["Id", "Role", "Start date", "Equipment", "What it supports"])
    fixtures = []
    for employee_id, role, start_cell, equipment, _purpose in rows:
        start_date = _first_date(start_cell, "start date")
        units = tuple(re.findall(r"([a-z]+) issued (\d{4}-\d{2}-\d{2})", equipment))
        if equipment != "none" and not units:
            raise AssertionError(f"unparsed equipment cell: {equipment}")
        fixtures.append((employee_id, role, start_date, units))
    return fixtures


def _first_date(cell: str, label: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", cell)
    if match is None:
        raise AssertionError(f"unparsed {label} cell: {cell}")
    return match.group(0)


def _probation_days(text: str) -> int:
    match = re.search(r"Probation length is \*\*(\d+) days\*\*", text)
    if match is None:
        raise AssertionError("probation_days not found in requirements.md")
    return int(match.group(1))


def _near_boundary_fraction(text: str) -> float:
    match = re.search(r"near_boundary_fraction = ([0-9.]+)", text)
    if match is None:
        raise AssertionError("near_boundary_fraction not found in requirements.md")
    return float(match.group(1))


def _hardware_terms(text: str) -> tuple[str, ...]:
    match = re.search(r"closed list: ([^\n]+)", text)
    if match is None:
        raise AssertionError("hardware failure list not found in requirements.md")
    return tuple(re.findall(r"`([^`]+)`", match.group(1)))
