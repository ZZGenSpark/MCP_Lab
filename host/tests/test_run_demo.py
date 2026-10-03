"""The demo keeps one server session and starts from an empty ticket file."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Self

from equipment_host.connection import flag_file, open_equipment_session
from equipment_host.react import RunResult
from equipment_host.run_demo import SCENARIOS, run_scenarios


def test_session_receives_the_flag_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCPLAB_AGENT_LOGS_DIR", str(tmp_path))
    session = open_equipment_session()
    env = session._params.env
    assert env is not None
    assert env["EQUIPMENT_FLAG_STORE"] == str(flag_file())


def test_the_demo_has_nine_scenarios_that_each_state_a_reason() -> None:
    names = [str(scenario["name"]) for scenario in SCENARIOS]
    assert len(names) == 9
    assert names == sorted(names)
    assert len(set(names)) == 9
    for scenario in SCENARIOS:
        assert "Reason:" in str(scenario["request"])
    assert [s["name"] for s in SCENARIOS if s["overcommit"]] == [
        "05_escalate_borderline_laptop"
    ]


def test_demo_reasons_come_from_the_requirements_scenario_table() -> None:
    doc = (Path(__file__).parents[2] / "docs" / "requirements.md").read_text(
        encoding="utf-8"
    )
    for scenario in SCENARIOS:
        match = re.search(r"Reason: (.+?) Today is", str(scenario["request"]))
        assert match is not None, scenario["name"]
        assert f'Reason: "{match.group(1)}"' in doc, scenario["name"]


def test_demo_covers_every_escalation_code_and_the_new_rules() -> None:
    names = {str(scenario["name"]) for scenario in SCENARIOS}
    assert {
        "07_escalate_data_conflict",
        "08_escalate_hardware_failure",
        "09_escalate_vague_request",
    } <= names


def test_demo_uses_one_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCPLAB_AGENT_LOGS_DIR", str(tmp_path))
    monkeypatch.setenv("MCPLAB_AGENT_TRACES_DIR", str(tmp_path / "traces"))
    opened: list[object] = []
    seen: list[object] = []

    class _Session:
        async def __aenter__(self) -> Self:
            opened.append(self)
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    async def fake_handle(request: str, llm: object, **kwargs: object) -> RunResult:
        seen.append(kwargs["session"])
        return RunResult(
            decision="approve",
            reason_code=None,
            text=request,
            trace=request,
            ticket_id=None,
            reflection={"verdict": "confirmed"},
        )

    monkeypatch.setattr(
        "equipment_host.run_demo.open_equipment_session", lambda: _Session()
    )
    monkeypatch.setattr("equipment_host.run_demo.handle_request", fake_handle)
    asyncio.run(run_scenarios())
    assert len(opened) == 1
    assert seen == [opened[0]] * len(SCENARIOS)
    assert flag_file().read_text(encoding="utf-8") == "[]\n"
    saved = list((tmp_path / "traces").glob("*.txt"))
    assert len(saved) == len(SCENARIOS) + 1
