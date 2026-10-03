"""ReAct loop with a scripted model and a fake tool session."""

from __future__ import annotations

import asyncio
import json

from equipment_host.llm import ChatReply, ScriptedLLM, tool_reply
from equipment_host.react import handle_request


def _action(name: str, arguments: dict) -> ChatReply:
    return tool_reply(name, arguments, "Check.")


def _final(decision: str, reason: str | None, text: str) -> ChatReply:
    body = {"decision": decision, "reason_code": reason, "text": text}
    return ChatReply(content=f"Decide.\n{json.dumps(body)}")


def _reflection(
    text: str, verdict: str = "confirmed", issues: list[str] | None = None
) -> str:
    return json.dumps({"verdict": verdict, "issues": issues or [], "final_text": text})


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
    assert "Call one tool" in llm.sent[1][-1]["content"]
    assert llm.tools[0]
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


TENURE_RULE = "hired 30 days ago, under the 90-day tenure minimum"
UNCLEAR_TENURE = {
    "ok": True,
    "eligible": "unclear",
    "reason_code": "TENURE_UNDER_90_DAYS",
    "rule": TENURE_RULE,
}
TICKET = {"ok": True, "ticket_id": "REV-0001", "status": "open"}
CHECK_ARGS = {"employee_id": "E1002", "item": "monitor"}


def _flag(reason: str) -> ChatReply:
    return _action(
        "flag_for_human_review",
        {
            "employee_id": "E1002",
            "request": "Please review E1002's request for a monitor.",
            "reason": reason,
        },
    )


def test_ticket_reason_is_rewritten_to_the_code_and_rule() -> None:
    text = f"Escalated (TENURE_UNDER_90_DAYS) as REV-0001. {TENURE_RULE}."
    session = FakeSession([UNCLEAR_TENURE, TICKET])
    llm = ScriptedLLM(
        [
            _action("check_request_eligibility", CHECK_ARGS),
            _flag("The employee is new"),
            _final("escalate", "TENURE_UNDER_90_DAYS", text),
            _reflection(text),
        ]
    )
    result = asyncio.run(handle_request("New hire asks", llm, session=session))
    expected = f"TENURE_UNDER_90_DAYS: {TENURE_RULE}"
    assert session.calls[1][1]["reason"] == expected
    assert f"Guardrail: ticket reason set to {expected!r}" in result.trace
    assert result.decision == "escalate"
    assert result.ticket_id == "REV-0001"
    assert result.reflection is not None
    assert result.reflection["verdict"] == "confirmed"
    assert "Reflection critique:" in result.trace


def test_a_bare_code_as_the_ticket_reason_gains_the_rule() -> None:
    text = f"Escalated (TENURE_UNDER_90_DAYS) as REV-0001. {TENURE_RULE}."
    session = FakeSession([UNCLEAR_TENURE, TICKET])
    llm = ScriptedLLM(
        [
            _action("check_request_eligibility", CHECK_ARGS),
            _flag("TENURE_UNDER_90_DAYS"),
            _final("escalate", "TENURE_UNDER_90_DAYS", text),
            _reflection(text),
        ]
    )
    asyncio.run(handle_request("New hire asks", llm, session=session))
    assert session.calls[1][1]["reason"] == f"TENURE_UNDER_90_DAYS: {TENURE_RULE}"


def test_a_ticket_reason_that_already_states_the_code_is_kept() -> None:
    reason = "TENURE_UNDER_90_DAYS: hired 30 days ago"
    text = f"Escalated (TENURE_UNDER_90_DAYS) as REV-0001. {TENURE_RULE}."
    session = FakeSession([UNCLEAR_TENURE, TICKET])
    llm = ScriptedLLM(
        [
            _action("check_request_eligibility", CHECK_ARGS),
            _flag(reason),
            _final("escalate", "TENURE_UNDER_90_DAYS", text),
            _reflection(text),
        ]
    )
    result = asyncio.run(handle_request("New hire asks", llm, session=session))
    assert session.calls[1][1]["reason"] == reason
    assert "ticket reason set to" not in result.trace


def test_an_escalation_text_without_ticket_or_reason_is_revised() -> None:
    text = "A person needs to look at your request."
    revised = (
        f"{text} Escalated for human review as REV-0001 "
        f"(TENURE_UNDER_90_DAYS): {TENURE_RULE}."
    )
    session = FakeSession([UNCLEAR_TENURE, TICKET])
    llm = ScriptedLLM(
        [
            _action("check_request_eligibility", CHECK_ARGS),
            _flag("TENURE_UNDER_90_DAYS: hired 30 days ago"),
            _final("escalate", "TENURE_UNDER_90_DAYS", text),
            _reflection(
                revised,
                "revised",
                ["The escalation draft does not state the ticket id."],
            ),
        ]
    )
    result = asyncio.run(handle_request("New hire asks", llm, session=session))
    assert result.reflection is not None
    assert result.reflection["verdict"] == "revised"
    assert result.text == revised
    assert "REV-0001" in result.text
    assert "TENURE_UNDER_90_DAYS" in result.text
    assert TENURE_RULE in result.text


def test_fallback_ticket_for_a_request_that_names_no_item() -> None:
    vague = {
        "ok": True,
        "eligible": "unclear",
        "reason_code": "VAGUE_REQUEST",
        "rule": "the request does not name an item",
    }
    session = FakeSession(
        [vague, {"ok": True, "employee_id": "E1001"}, TICKET, {"ok": True}]
    )
    llm = ScriptedLLM(
        [
            _action("check_request_eligibility", {"employee_id": "E1001", "item": ""}),
            _action("get_employee_info", {"employee_id": "E1001"}),
            _reflection("Escalated."),
        ]
    )
    result = asyncio.run(
        handle_request("Need some equipment", llm, session=session, max_steps=2)
    )
    name, arguments = session.calls[2]
    assert name == "flag_for_human_review"
    assert arguments["request"] == "E1001 sent a request that names no item."
    assert arguments["reason"] == "VAGUE_REQUEST: the request does not name an item"
    assert result.decision == "escalate"
    assert result.reason_code == "VAGUE_REQUEST"
    assert result.ticket_id == "REV-0001"


def test_fallback_ticket_names_the_item_that_was_requested() -> None:
    session = FakeSession([UNCLEAR_TENURE, TICKET])
    llm = ScriptedLLM(
        [
            _action("check_request_eligibility", CHECK_ARGS),
            _reflection("Escalated."),
        ]
    )
    asyncio.run(handle_request("New hire asks", llm, session=session, max_steps=1))
    arguments = session.calls[1][1]
    assert arguments["request"] == "Please review E1002's request for a monitor."
    assert arguments["reason"] == f"TENURE_UNDER_90_DAYS: {TENURE_RULE}"


def test_max_steps_stops_a_looping_model() -> None:
    session = FakeSession([{"ok": True, "employee_id": "E1001"}] * 10)
    llm = ScriptedLLM([_action("get_employee_info", {"employee_id": "E1001"})] * 10)
    result = asyncio.run(handle_request("Loop", llm, session=session, max_steps=3))
    assert result.decision == "unresolved"
    assert len(session.calls) == 3
    assert result.reflection is None
