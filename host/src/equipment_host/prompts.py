"""System, rethink, and reflection prompts for the ReAct loop."""

from __future__ import annotations

import json
from typing import Any

FORMAT_REMINDER = (
    "That reply was not in the required format. Send either "
    "'Thought: ...' and 'Action: tool_name {json}' or "
    "'Thought: ...' and 'Final: {json}'. Do not invent data."
)

ESCALATE_CODES = (
    "WITHIN_WINDOW_WITH_REASON",
    "TENURE_UNDER_90_DAYS",
    "DATA_CONFLICT",
    "VAGUE_REQUEST",
)


def system_prompt(tools: list[dict[str, Any]]) -> str:
    """Tell the model the tool schemas and the only two reply shapes."""
    catalog = json.dumps(tools, indent=2, default=str)
    codes = ", ".join(ESCALATE_CODES)
    return f"""You are an IT equipment request agent. Use only tool observations.
Do not invent employee ids, items, dates, or ticket ids.

Tools:
{catalog}

Reply with exactly one of these forms and nothing else:

Thought: <one sentence>
Action: <tool_name> <one JSON object>

Thought: <one sentence>
Final: {{"decision": "approve" or "deny" or "escalate", "reason_code": <string or null>, "text": "<reply>"}}

Decision rules:
- approve only when the last check_request_eligibility result has eligible true.
- deny when eligible is false and reason_code matches that result, or when
  EMPLOYEE_NOT_FOUND, UNKNOWN_ITEM, or UNKNOWN_ROLE is still failing after one retry.
  Do not call flag_for_human_review for those errors.
- escalate only when eligible is "unclear" and reason_code is one of {codes}.
  Call flag_for_human_review first and cite its ticket.
  Do not call flag_for_human_review when eligible is true or false.
  Copy reason_code from the eligibility observation into Final.
- On an error observation, fix the argument and retry that call once, or deny
  if the same non-retryable error remains. Do not invent a replacement id or item.
"""


def rethink_prompt(code: str, message: str) -> str:
    return (
        f"Observation (ERROR): The tool failed with code {code}. {message} "
        "Decide: fix the argument and retry, try another tool, or escalate. "
        "Do not invent data."
    )


def reflection_prompt(draft: str, decision: str, observations: str) -> str:
    return f"""Review this draft against the tool observations.

Decision: {decision}
Draft: {draft}
Observations: {observations}

Checklist:
1. Does every claim appear in an observation?
2. Does it promise anything not confirmed, such as a delivery date?
3. Is the decision consistent with the eligibility output?

Reply with only this JSON object:
{{"verdict": "confirmed" or "revised", "issues": ["..."], "final_text": "<reply>"}}
"""
