"""One scripted request leaves a readable host flow."""

from __future__ import annotations

import asyncio
import json

from equipment_host.llm import ChatReply, ScriptedLLM, tool_reply
from equipment_host.react import RunResult, handle_request
from equipment_host.run_one import main

import flowlog


class _Session:
    async def list_tools(self) -> list[dict]:
        return [
            {
                "name": "check_request_eligibility",
                "description": "Check one item",
                "input_schema": {"type": "object"},
            }
        ]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return {
            "ok": True,
            "eligible": True,
            "reason_code": None,
            "rule": "room in the window",
        }


def test_handle_request_logs_the_host_steps(tmp_path, monkeypatch) -> None:
    path = tmp_path / "run.log"
    monkeypatch.setenv(flowlog.ENV_PATH, str(path))
    text = "Approved for a monitor."
    final = {
        "decision": "approve",
        "reason_code": None,
        "text": text,
    }
    llm = ScriptedLLM(
        [
            tool_reply(
                "check_request_eligibility",
                {"employee_id": "E1001", "item": "monitor"},
                "Check.",
            ),
            ChatReply(content=f"Decide.\n{json.dumps(final)}"),
            json.dumps({"verdict": "confirmed", "issues": [], "final_text": text}),
        ]
    )
    result = asyncio.run(handle_request("Need a monitor", llm, session=_Session()))
    log = path.read_text(encoding="utf-8")
    assert result.decision == "approve"
    assert "host.llm.complete" in log
    assert "host.tool_call" in log
    assert "host.parse_decision" in log
    assert "host.react._act" in log
    assert "host.guardrails.evaluate" in log
    assert "host.reflect.reflect" in log
    assert "judge: no issues" in log
    assert "host.react._finish" in log
    assert log.index("host.llm.complete") < log.index("host.tool_call")
    assert log.index("host.tool_call") < log.index("calling check_request_eligibility")
    assert log.index("host.guardrails.evaluate") < log.index("host.react._finish")


def test_main_prints_the_flow_log_path(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MCPLAB_AGENT_LOGS_DIR", str(tmp_path))
    monkeypatch.delenv(flowlog.ENV_PATH, raising=False)

    async def fake_handle(request: str, llm: object, **kwargs: object) -> RunResult:
        flowlog.record("host", "llm.complete", request, None, "done")
        return RunResult(
            decision="approve",
            reason_code=None,
            text="Approved.",
            trace="Request: monitor",
            ticket_id=None,
            reflection={"verdict": "confirmed"},
        )

    monkeypatch.setattr("equipment_host.run_one.handle_request", fake_handle)
    main(["Employee", "E1001", "asks", "for", "a", "monitor."])
    logs = list(tmp_path.glob("*.log"))
    assert len(logs) == 1
    assert "Employee E1001 asks for a monitor." in logs[0].read_text(encoding="utf-8")
    assert f"flow log: {logs[0]}" in capsys.readouterr().out
