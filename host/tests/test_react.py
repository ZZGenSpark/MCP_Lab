"""ReAct loop with a scripted model and a fake tool session."""

from __future__ import annotations

import asyncio
import json

from equipment_host.llm import ScriptedLLM
from equipment_host.react import handle_request


def _action(name: str, arguments: dict) -> str:
    return f"Thought: Check.\nAction: {name} {json.dumps(arguments)}"


def _final(decision: str, reason: str | None, text: str) -> str:
    body = {"decision": decision, "reason_code": reason, "text": text}
    return f"Thought: Decide.\nFinal: {json.dumps(body)}"


def _reflection(text: str) -> str:
    return json.dumps({"verdict": "confirmed", "issues": [], "final_text": text})


class FakeSession:
    def __init__(self, results: list[dict]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self) -> list[dict]:
        return [
            {
                "name": "get_employee_info",
                "description": "Look up an employee",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        if not self._results:
            return {"ok": True}
        return self._results.pop(0)


def test_malformed_reply_is_retried_then_accepted() -> None:
    text = "Approved for a monitor."
    session = FakeSession(
        [
            {
                "ok": True,
                "eligible": True,
                "reason_code": None,
                "rule": "room in the window",
            }
        ]
    )
    llm = ScriptedLLM(
        [
            "hello there",
            _action(
                "check_request_eligibility", {"employee_id": "E1001", "item": "monitor"}
            ),
            _final("approve", None, text),
            _reflection(text),
        ]
    )
    result = asyncio.run(handle_request("Need a monitor", llm, session=session))
    assert result.decision == "approve"
    assert "required format" in llm.sent[1][-1]["content"]
    assert len(session.calls) == 1


def test_retry_cap_stops_a_third_call() -> None:
    error = {
        "ok": False,
        "error": {
            "code": "EMPLOYEE_NOT_FOUND",
            "message": "No employee with id E9999",
            "field": "employee_id",
            "retryable": False,
            "hint": "Check the id.",
        },
    }
    session = FakeSession([error, error, error, error])
    args = {"employee_id": "E9999"}
    text = "Denied. No employee matches that id."
    llm = ScriptedLLM(
        [
            _action("get_employee_info", args),
            _action("get_employee_info", args),
            _action("get_employee_info", args),
            _final("deny", "EMPLOYEE_NOT_FOUND", text),
            _reflection(text),
        ]
    )
    result = asyncio.run(
        handle_request("Unknown employee", llm, session=session, max_tool_retries=1)
    )
    assert result.decision == "deny"
    assert result.reason_code == "EMPLOYEE_NOT_FOUND"
    assert len(session.calls) == 2
    assert "Retry cap" in result.trace


def test_max_steps_stops_a_looping_model() -> None:
    session = FakeSession([{"ok": True, "employee_id": "E1001"}] * 10)
    llm = ScriptedLLM([_action("get_employee_info", {"employee_id": "E1001"})] * 10)
    result = asyncio.run(handle_request("Loop", llm, session=session, max_steps=3))
    assert result.decision == "unresolved"
    assert len(session.calls) == 3
    assert result.reflection is None
