"""ReAct loop: Thought, Action, Observation, then a guarded Final."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from equipment_client.session import EquipmentSession, transport_error

import config as root_config
from equipment_host.guardrails import (
    RETRYABLE,
    Evidence,
    evaluate,
    evidence_decision,
)
from equipment_host.llm import LLM
from equipment_host.parser import Action, Final, Malformed, parse_reply
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
    """Run one request. Opens a stdio session when the caller does not pass one."""
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
    async with EquipmentSession() as opened:
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
    tools = await session.list_tools()
    lines = [f"Request: {request}"]
    if not tools:
        lines.append("Could not list tools from the server.")
        return _finish(
            "system_fault",
            None,
            "The request could not be processed because of a system fault.",
            lines,
            Evidence(),
            None,
        )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt(tools)},
        {"role": "user", "content": request},
    ]
    evidence = Evidence()
    format_retries = 0
    guardrail_reprompts = 0
    draft: Final | None = None
    for _step in range(max_steps):
        reply = llm.complete(messages)
        messages.append({"role": "assistant", "content": reply})
        lines.append(reply.strip())
        parsed = parse_reply(reply)
        if isinstance(parsed, Malformed):
            format_retries += 1
            lines.append(f"Malformed: {parsed.message}")
            reminder = FORMAT_REMINDER
            if format_retries > 1:
                reminder = (
                    f"{FORMAT_REMINDER} Example: "
                    "Action: check_request_eligibility "
                    '{"employee_id": "E1001", "item": "monitor"}'
                )
            messages.append({"role": "user", "content": reminder})
            lines.append(reminder)
            continue
        format_retries = 0
        if isinstance(parsed, Action):
            fault = await _act(
                parsed, session, evidence, messages, lines, max_tool_retries
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
        if verdict.accepted:
            draft = parsed
            break
        lines.append(f"Guardrail: {verdict.message}")
        if guardrail_reprompts >= 1:
            draft = _override(parsed, verdict, evidence, max_tool_retries)
            lines.append(
                f"Guardrail override: {draft.decision} {draft.reason_code or ''}".rstrip()
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
    parsed: Action,
    session: ToolSession,
    evidence: Evidence,
    messages: list[dict[str, str]],
    lines: list[str],
    max_tool_retries: int,
) -> str | None:
    blocked = _blocked_flag(parsed, evidence)
    if blocked is not None:
        evidence.add(parsed.name, parsed.arguments, blocked)
        lines.append(f"Observation: {json.dumps(blocked)}")
        messages.append(
            {"role": "user", "content": f"Observation: {json.dumps(blocked)}"}
        )
        return None
    if evidence.error_count(parsed.name, parsed.arguments) > max_tool_retries:
        notice = (
            "Retry cap reached for this call. Choose a final decision from the "
            "observations you have. Do not invent data."
        )
        messages.append({"role": "user", "content": notice})
        lines.append(notice)
        return None
    try:
        result = await session.call_tool(parsed.name, parsed.arguments)
    except Exception as exc:  # noqa: BLE001
        result = transport_error(f"Tool call {parsed.name} failed: {exc}")
    evidence.add(parsed.name, parsed.arguments, result)
    lines.append(f"Observation: {json.dumps(result, default=str)}")
    if result.get("ok") is False:
        error = result.get("error", {})
        code = str(error.get("code") or "UNKNOWN")
        lines.append(f"Observation (ERROR): {code}")
        if (
            code in RETRYABLE
            and evidence.error_count(parsed.name, parsed.arguments) > max_tool_retries
        ):
            lines.append("System fault: the retryable error persisted.")
            return "system_fault"
        hint = str(error.get("message") or "")
        messages.append(
            {
                "role": "user",
                "content": f"Observation (ERROR): {rethink_prompt(code, hint)}",
            }
        )
        return None
    messages.append(
        {"role": "user", "content": f"Observation: {json.dumps(result, default=str)}"}
    )
    return None


def _coerce(parsed: Final, evidence: Evidence) -> tuple[str, str | None]:
    """Fill a missing escalation code from the eligibility observation."""
    if parsed.decision != "escalate" or parsed.reason_code in {
        "WITHIN_WINDOW_WITH_REASON",
        "TENURE_UNDER_90_DAYS",
        "DATA_CONFLICT",
        "VAGUE_REQUEST",
    }:
        return parsed.decision, parsed.reason_code
    eligibility = evidence.last("check_request_eligibility")
    if not isinstance(eligibility, dict):
        return parsed.decision, parsed.reason_code
    reason = eligibility.get("reason_code")
    if eligibility.get("eligible") == "unclear" and isinstance(reason, str):
        return parsed.decision, reason
    return parsed.decision, parsed.reason_code


def _blocked_flag(parsed: Action, evidence: Evidence) -> dict[str, Any] | None:
    """Do not open a ticket when eligibility is already true or false."""
    if parsed.name != "flag_for_human_review":
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
    if reason not in {
        "WITHIN_WINDOW_WITH_REASON",
        "TENURE_UNDER_90_DAYS",
        "DATA_CONFLICT",
        "VAGUE_REQUEST",
    }:
        return
    employee_id = observed.arguments.get("employee_id")
    item = observed.arguments.get("item")
    if not isinstance(employee_id, str) or not isinstance(item, str):
        return
    arguments = {
        "employee_id": employee_id,
        "request": f"Please review a {item}.",
        "reason": reason,
    }
    lines.append(
        "Guardrail: eligibility is unclear, so flag_for_human_review is required."
    )
    try:
        result = await session.call_tool("flag_for_human_review", arguments)
    except Exception as exc:  # noqa: BLE001
        result = transport_error(f"Tool call flag_for_human_review failed: {exc}")
    evidence.add("flag_for_human_review", arguments, result)
    lines.append(f"Observation: {json.dumps(result, default=str)}")


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
    return RunResult(
        decision=decision,
        reason_code=reason_code,
        text=text,
        trace="\n".join(lines),
        ticket_id=ticket_id,
        reflection=reflection,
        tool_calls=[(item.tool, item.arguments) for item in evidence.observations],
    )
