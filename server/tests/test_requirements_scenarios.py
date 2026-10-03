"""Every row of the scenario table in docs/requirements.md, run on the real tool.

The rows are parsed from the document, so a scenario added there is tested
here without editing this file, and the policy and the tool cannot drift.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from equipment_server.tools import check_request_eligibility

REQUIREMENTS = Path(__file__).resolve().parents[2] / "docs" / "requirements.md"
HEADING = "## Scenarios the policy must produce"
TODAY = date(2026, 1, 1)
ESCALATION_CODES = {
    "WITHIN_WINDOW_WITH_REASON",
    "TENURE_UNDER_90_DAYS",
    "DATA_CONFLICT",
    "VAGUE_REQUEST",
}

Row = tuple[str, str, str, str, str | None]


def _scenarios() -> list[Row]:
    section = REQUIREMENTS.read_text(encoding="utf-8").split(HEADING, 1)[1]
    rows: list[Row] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [
            cell.strip().replace("`", "") for cell in line.strip("| \n").split("|")
        ]
        if cells[0] in {"Request"} or set(cells[0]) <= {"-", " "}:
            continue
        request, outcome, code = cells
        employee = re.search(r"\bE\d{4}\b", request)
        reason = re.search(r'Reason: "(.*)"', request)
        assert employee is not None, f"no employee id in: {request}"
        assert reason is not None, f"no reason in: {request}"
        if "names no item" in request:
            item = ""
        else:
            named = re.search(r"asks for an? (.+?)\.", request)
            assert named is not None, f"no item in: {request}"
            item = named.group(1)
        rows.append(
            (
                employee.group(0),
                item,
                reason.group(1),
                outcome,
                None if code in {"—", "–", "-"} else code,
            )
        )
    return rows


def _actual(result: dict[str, object]) -> tuple[str, object]:
    if result["ok"] is False:
        error = result["error"]
        assert isinstance(error, dict)
        return "Deny", error["code"]
    if result["eligible"] is True:
        return "Approve", None
    if result["eligible"] is False:
        return "Deny", result["reason_code"]
    return "Escalate", result["reason_code"]


SCENARIOS = _scenarios()


def test_the_table_was_parsed() -> None:
    assert len(SCENARIOS) >= 10


@pytest.mark.parametrize(
    ("employee", "item", "reason", "outcome", "code"),
    SCENARIOS,
    ids=[f"{row[0]}-{row[1] or 'no-item'}-{row[3]}-{row[4]}" for row in SCENARIOS],
)
def test_scenario_matches_the_document(
    employee: str, item: str, reason: str, outcome: str, code: str | None
) -> None:
    result = check_request_eligibility(employee, item, reason, today=TODAY)
    assert _actual(result) == (outcome, code)


def test_every_escalation_code_has_a_scenario() -> None:
    escalated = {row[4] for row in SCENARIOS if row[3] == "Escalate"}
    assert escalated == ESCALATION_CODES
