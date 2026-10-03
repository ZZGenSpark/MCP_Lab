"""ReAct loop: Thought, Action, Observation, then a guarded Final."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from equipment_client.session import transport_error

import config as root_config
import flowlog
from equipment_host.connection import open_equipment_session
from equipment_host.guardrails import (
    ESCALATE_CODES,
    RETRYABLE,
    Evidence,
    evaluate,
    evidence_decision,
)
from equipment_host.llm import LLM, ToolCall, ollama_tools
from equipment_host.parser import Final, Malformed, parse_decision
from equipment_host.prompts import FORMAT_REMINDER, rethink_prompt, system_prompt
from equipment_host.reflect import reflect


class ToolSession(Protocol):
    async def list_tools(self) -> list[dict[str, Any]]:
        """Return tool name, description, and input schema."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return the tool dict, including ok: false errors."""


@dataclass
class RunResult:
    decision: str
    reason_code: str | None
    text: str
    trace: str
    ticket_id: str | None
    reflection: dict[str, object] | None
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


async def handle_request(
    request: str,
    llm: LLM,
    *,
    session: ToolSession | None = None,
    max_steps: int | None = None,
    max_tool_retries: int | None = None,
    inject_overcommit: bool = False,
) -> RunResult:
    """Run one request. Opens one stdio server when the caller does not pass one."""
    cfg = root_config.load_config()
    steps = cfg.agent.max_steps if max_steps is None else max_steps
    retries = (
        cfg.agent.max_tool_retries if max_tool_retries is None else max_tool_retries
    )
    if session is not None:
        return await _run(
            request,
            llm,
            session,
            max_steps=steps,
            max_tool_retries=retries,
            inject_overcommit=inject_overcommit,
        )
    async with open_equipment_session() as opened:
        return await _run(
            request,
            llm,
            opened,
            max_steps=steps,
            max_tool_retries=retries,
            inject_overcommit=inject_overcommit,
        )


async def _run(
    request: str,
    llm: LLM,
    session: ToolSession,
    *,
    max_steps: int,
    max_tool_retries: int,
    inject_overcommit: bool,
) -> RunResult:
    flowlog.record(
        "host",
        "react._run",
        request,
        None,
        "opening the client session and listing tools",
    )
    tools = await session.list_tools()
    lines = [f"Request: {request}"]
    if not tools:
        lines.append("Could not list tools from the server.")
        flowlog.record(
            "host",
            "react._run",
            [],
            ["list_tools returned no tools"],
            "stopping as system_fault",
        )
        return _finish(
            "system_fault",
            None,
            "The request could not be processed because of a system fault.",
            lines,
            Evidence(),
            None,
        )
    flowlog.record(
        "host",
        "react._run",
        [tool["name"] for tool in tools],
        None,
        "starting the ReAct loop",
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(tools)},
        {"role": "user", "content": request},
    ]
    tool_defs = ollama_tools(tools)
    evidence = Evidence()
    format_retries = 0
    guardrail_reprompts = 0
    draft: Final | None = None
    for _step in range(max_steps):
        previous = messages[-1].get("content")
        reply = llm.complete(messages, tool_defs)
        flowlog.record(
            "host",
            "llm.complete",
            previous,
            None,
            {"content": reply.content, "tool_calls": _call_log(reply.tool_calls)},
        )
        if reply.tool_calls:
            call = reply.tool_calls[0]
            thought = reply.content.strip() or f"Call {call.name}."
            lines.append(f"Thought: {thought}")
            lines.append(f"Action: {call.name} {json.dumps(call.arguments)}")
            messages.append(_assistant_tool_message(reply.content, call))
            flowlog.record(
                "host",
                "tool_call",
                reply.content,
                None,
                f"Action: {call.name} {json.dumps(call.arguments)}",
            )
            fault = await _act(
                call, session, evidence, messages, lines, max_tool_retries
            )
            if fault is not None:
                return _finish(
                    "system_fault",
                    None,
                    "The request could not be processed because of a system fault.",
                    lines,
                    evidence,
                    None,
                )
            continue
        messages.append({"role": "assistant", "content": reply.content})
        parsed = parse_decision(reply.content)
        flowlog.record(
            "host", "parse_decision", reply.content, None, _parsed_text(parsed)
        )
        if isinstance(parsed, Malformed):
            format_retries += 1
            lines.append(f"Malformed: {parsed.message}")
            reminder = FORMAT_REMINDER
            if format_retries > 1:
                reminder = (
                    f"{FORMAT_REMINDER} Example: "
                    '{"decision": "approve", "reason_code": null, '
                    '"text": "Approved for a monitor."}'
                )
            messages.append({"role": "user", "content": reminder})
            lines.append(reminder)
            flowlog.record(
                "host",
                "react._run",
                parsed.message,
                ["reply was malformed"],
                reminder,
            )
            continue
        format_retries = 0
        thought = parsed.thought or "Decide from the observations."
        lines.append(f"Thought: {thought}")
        lines.append(
            "Final: "
            + json.dumps(
                {
                    "decision": parsed.decision,
                    "reason_code": parsed.reason_code,
                    "text": parsed.text,
                }
            )
        )
        decision, reason_code = _coerce(parsed, evidence)
        verdict = evaluate(
            decision,
            reason_code,
            evidence,
            max_tool_retries=max_tool_retries,
        )
        parsed = Final(
            decision=decision,
            reason_code=reason_code,
            text=parsed.text,
            thought=parsed.thought,
        )
        flowlog.record(
            "host",
            "guardrails.evaluate",
            _parsed_text(parsed),
            [verdict.message],
            {
                "accepted": verdict.accepted,
                "override_decision": verdict.override_decision,
                "override_reason": verdict.override_reason,
            },
        )
        if verdict.accepted:
            draft = parsed
            break
        lines.append(f"Guardrail: {verdict.message}")
        if guardrail_reprompts >= 1:
            draft = _override(parsed, verdict, evidence, max_tool_retries)
            lines.append(
                f"Guardrail override: {draft.decision} {draft.reason_code or ''}".rstrip()
            )
            flowlog.record(
                "host",
                "guardrails.evaluate",
                verdict.message,
                ["re-prompt already used"],
                {
                    "decision": draft.decision,
                    "reason_code": draft.reason_code,
                    "text": draft.text,
                },
            )
            break
        guardrail_reprompts += 1
        messages.append({"role": "user", "content": verdict.message})
    if draft is None:
        await _open_required_ticket(session, evidence, lines)
        decision, reason_code, text = evidence_decision(
            evidence, max_tool_retries=max_tool_retries
        )
        if decision not in {"approve", "deny", "escalate"}:
            return _finish(
                "unresolved",
                None,
                "The request stopped before a decision.",
                lines,
                evidence,
                None,
            )
        draft = Final(decision=decision, reason_code=reason_code, text=text, thought="")
        lines.append(
            f"Guardrail override: {draft.decision} {draft.reason_code or ''}".rstrip()
        )
    text = draft.text
    if inject_overcommit:
        text = f"{text} The replacement will ship tomorrow."
        lines.append(f"Draft (over-commit injected): {text}")
    else:
        lines.append(f"Draft: {text}")
    reviewed = reflect(text, draft.decision, evidence, llm)
    issues = reviewed.get("issues")
    flowlog.record(
        "host",
        "reflect.reflect",
        text,
        issues if isinstance(issues, list) and issues else ["judge: no issues"],
        {
            "verdict": reviewed.get("verdict"),
            "final_text": reviewed.get("final_text"),
        },
    )
    lines.append(f"Reflection critique: {reviewed['critique']}")
    lines.append(
        f"Reflection: {reviewed['verdict']} issues={json.dumps(reviewed['issues'])}"
    )
    lines.append(f"Final: {reviewed['final_text']}")
    lines.append(f"Decision: {draft.decision} {draft.reason_code or ''}".rstrip())
    return _finish(
        draft.decision,
        draft.reason_code,
        str(reviewed["final_text"]),
        lines,
        evidence,
        reviewed,
    )


async def _act(
    call: ToolCall,
    session: ToolSession,
    evidence: Evidence,
    messages: list[dict[str, Any]],
    lines: list[str],
    max_tool_retries: int,
) -> str | None:
    called = {"name": call.name, "arguments": call.arguments}
    blocked = _blocked_flag(call, evidence)
    if blocked is not None:
        evidence.add(call.name, call.arguments, blocked)
        lines.append(f"Observation: {json.dumps(blocked)}")
        _tool_message(messages, call.name, json.dumps(blocked))
        flowlog.record(
            "host",
            "react._act",
            called,
            ["blocked flag_for_human_review: eligibility is not unclear"],
            blocked,
        )
        return None
    rewritten = _with_ticket_reason(call, evidence)
    if rewritten is not call:
        lines.append(
            f"Guardrail: ticket reason set to {rewritten.arguments['reason']!r}"
        )
        flowlog.record(
            "host",
            "react._act",
            called,
            ["ticket reason did not state the eligibility code and rule"],
            {"name": rewritten.name, "arguments": rewritten.arguments},
        )
        call = rewritten
        called = {"name": call.name, "arguments": call.arguments}
    if evidence.error_count(call.name, call.arguments) > max_tool_retries:
        notice = (
            "Retry cap reached for this call. Choose a final decision from the "
            "observations you have. Do not invent data."
        )
        _tool_message(messages, call.name, notice)
        lines.append(notice)
        flowlog.record(
            "host",
            "react._act",
            called,
            ["retry cap reached for this call"],
            notice,
        )
        return None
    flowlog.record("host", "react._act", called, None, f"calling {call.name}")
    try:
        result = await session.call_tool(call.name, call.arguments)
    except Exception as exc:  # noqa: BLE001
        result = transport_error(f"Tool call {call.name} failed: {exc}")
    evidence.add(call.name, call.arguments, result)
    lines.append(f"Observation: {json.dumps(result, default=str)}")
    if result.get("ok") is False:
        error = result.get("error", {})
        code = str(error.get("code") or "UNKNOWN")
        lines.append(f"Observation (ERROR): {code}")
        if (
            code in RETRYABLE
            and evidence.error_count(call.name, call.arguments) > max_tool_retries
        ):
            lines.append("System fault: the retryable error persisted.")
            _tool_message(messages, call.name, json.dumps(result, default=str))
            flowlog.record(
                "host",
                "react._act",
                result,
                [f"retryable error {code} persisted"],
                "system_fault",
            )
            return "system_fault"
        hint = str(error.get("message") or "")
        _tool_message(
            messages,
            call.name,
            f"{rethink_prompt(code, hint)}\n{json.dumps(result, default=str)}",
        )
        flowlog.record(
            "host",
            "react._act",
            result,
            [f"tool error {code}"],
            "error observation added to the prompt",
        )
        return None
    _tool_message(messages, call.name, json.dumps(result, default=str))
    flowlog.record(
        "host",
        "react._act",
        result,
        None,
        "observation added to the prompt",
    )
    return None


def _assistant_tool_message(content: str, call: ToolCall) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
        ],
    }


def _tool_message(messages: list[dict[str, Any]], name: str, content: str) -> None:
    messages.append({"role": "tool", "tool_name": name, "content": content})


def _call_log(calls: tuple[ToolCall, ...]) -> list[dict[str, Any]]:
    return [{"name": call.name, "arguments": call.arguments} for call in calls]


def _parsed_text(parsed: Final | Malformed) -> str:
    if isinstance(parsed, Malformed):
        return f"Malformed: {parsed.message}"
    return (
        f"Final: decision={parsed.decision} "
        f"reason={parsed.reason_code} text={parsed.text}"
    )


def _coerce(parsed: Final, evidence: Evidence) -> tuple[str, str | None]:
    """Fill a missing escalation code from the eligibility observation."""
    if parsed.decision != "escalate" or parsed.reason_code in ESCALATE_CODES:
        return parsed.decision, parsed.reason_code
    eligibility = evidence.last("check_request_eligibility")
    if not isinstance(eligibility, dict):
        return parsed.decision, parsed.reason_code
    reason = eligibility.get("reason_code")
    if eligibility.get("eligible") == "unclear" and isinstance(reason, str):
        return parsed.decision, reason
    return parsed.decision, parsed.reason_code


def _ticket_reason(code: str, rule: object) -> str:
    """The reason written on a review ticket: the code, then the rule behind it."""
    return f"{code}: {rule}" if isinstance(rule, str) and rule else code


def _with_ticket_reason(call: ToolCall, evidence: Evidence) -> ToolCall:
    """Make a ticket reason say why, using the last eligibility observation.

    A reason that already starts with the code is left alone. Anything else,
    such as a bare code or a vague phrase, becomes "<code>: <rule>". The
    VAGUE_REQUEST prefix also lets the server accept a ticket with no item.
    """
    if call.name != "flag_for_human_review":
        return call
    eligibility = evidence.last("check_request_eligibility")
    if not isinstance(eligibility, dict) or eligibility.get("eligible") != "unclear":
        return call
    code = eligibility.get("reason_code")
    if not isinstance(code, str) or code not in ESCALATE_CODES:
        return call
    current = call.arguments.get("reason")
    if isinstance(current, str) and current.strip().startswith(f"{code}:"):
        return call
    arguments = dict(call.arguments)
    arguments["reason"] = _ticket_reason(code, eligibility.get("rule"))
    return ToolCall(call.name, arguments)


def _blocked_flag(call: ToolCall, evidence: Evidence) -> dict[str, Any] | None:
    """Do not open a ticket when eligibility is already true or false."""
    if call.name != "flag_for_human_review":
        return None
    eligibility = evidence.last("check_request_eligibility")
    if isinstance(eligibility, dict) and eligibility.get("eligible") == "unclear":
        return None
    return {
        "ok": False,
        "error": {
            "code": "NOT_ESCALATED",
            "message": "Open a ticket only after eligibility is unclear.",
            "field": "request",
            "retryable": False,
            "hint": "Approve when eligible is true. Deny when eligible is false.",
        },
    }


async def _open_required_ticket(
    session: ToolSession, evidence: Evidence, lines: list[str]
) -> None:
    """Open the review ticket when policy is unclear and the model never flagged."""
    if evidence.successful_flag() is not None:
        return
    observed = evidence.last_observation("check_request_eligibility")
    if observed is None or observed.result.get("eligible") != "unclear":
        return
    reason = observed.result.get("reason_code")
    if reason not in ESCALATE_CODES:
        return
    employee_id = observed.arguments.get("employee_id")
    item = observed.arguments.get("item")
    if not isinstance(employee_id, str):
        return
    named = item.strip() if isinstance(item, str) else ""
    request = (
        f"Please review {employee_id}'s request for a {named}."
        if named
        else f"{employee_id} sent a request that names no item."
    )
    arguments = {
        "employee_id": employee_id,
        "request": request,
        "reason": _ticket_reason(reason, observed.result.get("rule")),
    }
    lines.append(
        "Guardrail: eligibility is unclear, so flag_for_human_review is required."
    )
    flowlog.record(
        "host",
        "react._open_required_ticket",
        observed.result,
        ["eligibility is unclear and no ticket is open"],
        arguments,
    )
    try:
        result = await session.call_tool("flag_for_human_review", arguments)
    except Exception as exc:  # noqa: BLE001
        result = transport_error(f"Tool call flag_for_human_review failed: {exc}")
    evidence.add("flag_for_human_review", arguments, result)
    lines.append(f"Observation: {json.dumps(result, default=str)}")
    flowlog.record(
        "host",
        "react._open_required_ticket",
        result,
        None,
        "ticket observation added",
    )


def _override(
    parsed: Final, verdict: Any, evidence: Evidence, max_tool_retries: int
) -> Final:
    if verdict.override_decision:
        return Final(
            decision=verdict.override_decision,
            reason_code=verdict.override_reason,
            text=verdict.override_text or parsed.text,
            thought=parsed.thought,
        )
    decision, reason, text = evidence_decision(
        evidence, max_tool_retries=max_tool_retries
    )
    if decision not in {"approve", "deny", "escalate"}:
        return Final(decision="deny", reason_code=reason, text=text, thought="")
    return Final(decision=decision, reason_code=reason, text=text, thought="")


def _finish(
    decision: str,
    reason_code: str | None,
    text: str,
    lines: list[str],
    evidence: Evidence,
    reflection: dict[str, object] | None,
) -> RunResult:
    ticket = evidence.successful_flag()
    ticket_id = None if ticket is None else ticket.get("ticket_id")
    if not isinstance(ticket_id, str):
        ticket_id = None
    lines.append(f"Outcome: {decision}")
    flowlog.record(
        "host",
        "react._finish",
        text,
        None,
        {
            "decision": decision,
            "reason_code": reason_code,
            "ticket_id": ticket_id,
            "text": text,
        },
    )
    return RunResult(
        decision=decision,
        reason_code=reason_code,
        text=text,
        trace="\n".join(lines),
        ticket_id=ticket_id,
        reflection=reflection,
        tool_calls=[(item.tool, item.arguments) for item in evidence.observations],
    )
