"""Host, client, and the real server. Only the model is scripted."""

from __future__ import annotations

import asyncio

import pytest
from equipment_client.session import EquipmentSession
from equipment_host.react import RunResult, handle_request

from tests_e2e.conftest import kill_equipment_servers, scripted
from tests_e2e.protocol import action, final, reflection

APPROVE_TEXT = "E1001 may have a first monitor. The refresh window has room."
DENY_LAPTOP = "A contractor cannot request a laptop."
DENY_MISSING = "No employee E9999. Please resubmit with a valid id."
DENY_DESK = (
    "A standing desk is not requestable. "
    "Requestable items: monitor, laptop, keyboard, mouse, dock, headset."
)
ESCALATE_LAPTOP = (
    "Escalated (WITHIN_WINDOW_WITH_REASON) as REV-0001. "
    "The laptop is inside the refresh window and needs review."
)
ESCALATE_HIRE = (
    "Escalated (TENURE_UNDER_90_DAYS) as REV-0001. "
    "The new hire needs manager sign-off before a monitor is issued."
)
ESCALATE_CONFLICT = (
    "Escalated (DATA_CONFLICT) as REV-0001. "
    "The contractor already holds a laptop on file, which that role cannot have."
)
ESCALATE_BROKEN = (
    "Escalated (WITHIN_WINDOW_WITH_REASON) as REV-0001. "
    "The monitor is inside its window, but the reason reports a hardware failure."
)
ESCALATE_VAGUE = (
    "Escalated (VAGUE_REQUEST) as REV-0001. "
    "The request does not name an item, so a person needs to follow up."
)
DENY_SECOND_SCREEN = "Denied (LIMIT_REACHED). The standard role already has a monitor."


def _run(
    replies: list, *, overcommit: bool = False, steps: int | None = None
) -> RunResult:
    return asyncio.run(_open(replies, overcommit=overcommit, steps=steps))


async def _open(
    replies: list, *, overcommit: bool, steps: int | None = None
) -> RunResult:
    async with EquipmentSession(timeout=5) as session:
        return await handle_request(
            "See the scripted actions.",
            scripted(replies),
            session=session,
            inject_overcommit=overcommit,
            max_steps=steps,
        )


def _ticket_args(result: RunResult) -> dict:
    """The arguments of the ticket the run opened."""
    for name, arguments in result.tool_calls:
        if name == "flag_for_human_review":
            return arguments
    raise AssertionError("the run opened no ticket")


def test_approve_first_monitor() -> None:
    text = APPROVE_TEXT
    result = _run(
        [
            action("get_employee_info", {"employee_id": "E1001"}),
            action(
                "check_request_eligibility",
                {"employee_id": "E1001", "item": "monitor"},
            ),
            final("approve", None, text),
            reflection(text),
        ]
    )
    assert result.decision == "approve"
    assert result.reason_code is None
    assert result.ticket_id is None
    assert "flag_for_human_review" not in {name for name, _args in result.tool_calls}
    assert result.reflection is not None
    assert result.reflection["verdict"] == "confirmed"


def test_deny_contractor_laptop() -> None:
    result = _run(
        [
            action("get_employee_info", {"employee_id": "E1002"}),
            action(
                "check_request_eligibility",
                {"employee_id": "E1002", "item": "laptop"},
            ),
            final("deny", "ROLE_NOT_ELIGIBLE", DENY_LAPTOP),
            reflection(DENY_LAPTOP),
        ]
    )
    assert result.decision == "deny"
    assert result.reason_code == "ROLE_NOT_ELIGIBLE"
    assert result.ticket_id is None


def test_deny_unknown_employee_after_one_retry() -> None:
    result = _run(
        [
            action("get_employee_info", {"employee_id": "E9999"}),
            action("get_employee_info", {"employee_id": "E9999"}),
            final("deny", "EMPLOYEE_NOT_FOUND", DENY_MISSING),
            reflection(DENY_MISSING),
        ]
    )
    assert result.decision == "deny"
    assert result.reason_code == "EMPLOYEE_NOT_FOUND"
    assert result.ticket_id is None
    assert result.tool_calls == [
        ("get_employee_info", {"employee_id": "E9999"}),
        ("get_employee_info", {"employee_id": "E9999"}),
    ]
    assert result.trace.count("Observation (ERROR): EMPLOYEE_NOT_FOUND") == 2


def test_deny_unknown_item_lists_the_catalog() -> None:
    result = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1001", "item": "standing desk"},
            ),
            action(
                "check_request_eligibility",
                {"employee_id": "E1001", "item": "desk"},
            ),
            final("deny", "UNKNOWN_ITEM", DENY_DESK),
            reflection(DENY_DESK),
        ]
    )
    assert result.decision == "deny"
    assert result.reason_code == "UNKNOWN_ITEM"
    assert "monitor" in result.text
    assert "headset" in result.text
    assert result.ticket_id is None


def test_escalate_borderline_laptop() -> None:
    result = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1003", "item": "laptop"},
            ),
            action(
                "flag_for_human_review",
                {
                    "employee_id": "E1003",
                    "request": "Please review the laptop.",
                    "reason": "WITHIN_WINDOW_WITH_REASON",
                },
            ),
            final("escalate", "WITHIN_WINDOW_WITH_REASON", ESCALATE_LAPTOP),
            reflection(ESCALATE_LAPTOP),
        ]
    )
    assert result.decision == "escalate"
    assert result.reason_code == "WITHIN_WINDOW_WITH_REASON"
    assert result.ticket_id == "REV-0001"


def test_escalate_new_hire() -> None:
    result = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1004", "item": "monitor"},
            ),
            action(
                "flag_for_human_review",
                {
                    "employee_id": "E1004",
                    "request": "Please review a monitor for a new hire.",
                    "reason": "TENURE_UNDER_90_DAYS",
                },
            ),
            final("escalate", "TENURE_UNDER_90_DAYS", ESCALATE_HIRE),
            reflection(ESCALATE_HIRE),
        ]
    )
    assert result.decision == "escalate"
    assert result.reason_code == "TENURE_UNDER_90_DAYS"
    assert result.ticket_id == "REV-0001"


def test_escalate_data_conflict() -> None:
    reason = "My laptop no longer works."
    result = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1005", "item": "laptop", "reason": reason},
            ),
            action(
                "flag_for_human_review",
                {
                    "employee_id": "E1005",
                    "request": "Please review E1005's request for a laptop.",
                    "reason": "DATA_CONFLICT",
                },
            ),
            final("escalate", "DATA_CONFLICT", ESCALATE_CONFLICT),
            reflection(ESCALATE_CONFLICT),
        ]
    )
    assert result.decision == "escalate"
    assert result.reason_code == "DATA_CONFLICT"
    assert result.ticket_id == "REV-0001"
    assert _ticket_args(result)["reason"].startswith("DATA_CONFLICT: ")
    assert result.reflection is not None
    assert result.reflection["verdict"] == "confirmed"


def test_escalate_a_reported_hardware_failure() -> None:
    result = _run(
        [
            action(
                "check_request_eligibility",
                {
                    "employee_id": "E1006",
                    "item": "monitor",
                    "reason": "My monitor is broken.",
                },
            ),
            action(
                "flag_for_human_review",
                {
                    "employee_id": "E1006",
                    "request": "Please review E1006's request for a monitor.",
                    "reason": "WITHIN_WINDOW_WITH_REASON",
                },
            ),
            final("escalate", "WITHIN_WINDOW_WITH_REASON", ESCALATE_BROKEN),
            reflection(ESCALATE_BROKEN),
        ]
    )
    assert result.decision == "escalate"
    assert result.reason_code == "WITHIN_WINDOW_WITH_REASON"
    assert result.ticket_id == "REV-0001"
    assert "hardware failure" in _ticket_args(result)["reason"]


def test_a_second_screen_without_a_failure_is_denied() -> None:
    result = _run(
        [
            action(
                "check_request_eligibility",
                {
                    "employee_id": "E1006",
                    "item": "monitor",
                    "reason": "I would like a second screen.",
                },
            ),
            final("deny", "LIMIT_REACHED", DENY_SECOND_SCREEN),
            reflection(DENY_SECOND_SCREEN),
        ]
    )
    assert result.decision == "deny"
    assert result.reason_code == "LIMIT_REACHED"
    assert result.ticket_id is None


def test_escalate_a_vague_request_with_no_item() -> None:
    result = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1001", "item": "", "reason": "Help."},
            ),
            action(
                "flag_for_human_review",
                {
                    "employee_id": "E1001",
                    "request": "E1001 sent a request that names no item.",
                    "reason": "VAGUE_REQUEST",
                },
            ),
            final("escalate", "VAGUE_REQUEST", ESCALATE_VAGUE),
            reflection(ESCALATE_VAGUE),
        ]
    )
    assert result.decision == "escalate"
    assert result.reason_code == "VAGUE_REQUEST"
    assert result.ticket_id == "REV-0001"
    assert _ticket_args(result)["reason"] == (
        "VAGUE_REQUEST: the request does not name an item"
    )


def test_ticket_reason_states_the_code_and_the_rule() -> None:
    result = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1004", "item": "monitor"},
            ),
            action(
                "flag_for_human_review",
                {
                    "employee_id": "E1004",
                    "request": "Please review a monitor for a new hire.",
                    "reason": "TENURE_UNDER_90_DAYS",
                },
            ),
            final("escalate", "TENURE_UNDER_90_DAYS", ESCALATE_HIRE),
            reflection(ESCALATE_HIRE),
        ]
    )
    reason = _ticket_args(result)["reason"]
    assert reason.startswith("TENURE_UNDER_90_DAYS: ")
    assert len(reason) > len("TENURE_UNDER_90_DAYS: ")
    assert "Guardrail: ticket reason set to" in result.trace


def test_an_escalation_text_without_ticket_or_reason_is_revised() -> None:
    thin = "A person needs to look at your request."
    result = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1004", "item": "monitor"},
            ),
            action(
                "flag_for_human_review",
                {
                    "employee_id": "E1004",
                    "request": "Please review a monitor for a new hire.",
                    "reason": "TENURE_UNDER_90_DAYS",
                },
            ),
            final("escalate", "TENURE_UNDER_90_DAYS", thin),
            reflection(
                (
                    f"{thin} Escalated for human review as REV-0001 "
                    "(TENURE_UNDER_90_DAYS)."
                ),
                "revised",
                ["The escalation draft does not state the ticket id."],
            ),
        ]
    )
    assert result.reflection is not None
    assert result.reflection["verdict"] == "revised"
    assert result.text.startswith(thin)
    assert "REV-0001" in result.text
    assert "TENURE_UNDER_90_DAYS" in result.text


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        ({"employee_id": "E1003", "item": "laptop"}, "WITHIN_WINDOW_WITH_REASON"),
        ({"employee_id": "E1004", "item": "monitor"}, "TENURE_UNDER_90_DAYS"),
        ({"employee_id": "E1005", "item": "laptop"}, "DATA_CONFLICT"),
        (
            {
                "employee_id": "E1006",
                "item": "monitor",
                "reason": "My monitor is broken.",
            },
            "WITHIN_WINDOW_WITH_REASON",
        ),
        ({"employee_id": "E1001", "item": "", "reason": "Help."}, "VAGUE_REQUEST"),
    ],
)
def test_host_opens_an_accepted_ticket_when_the_model_never_does(
    arguments: dict, code: str
) -> None:
    result = _run(
        [action("check_request_eligibility", arguments), reflection("Escalated.")],
        steps=1,
    )
    assert result.decision == "escalate"
    assert result.reason_code == code
    assert result.ticket_id == "REV-0001"
    assert _ticket_args(result)["reason"].startswith(f"{code}: ")
    assert result.reflection is not None
    assert result.reflection["verdict"] == "confirmed"


def test_guardrail_overrides_a_bad_approve_and_a_bad_escalation() -> None:
    approved = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1002", "item": "laptop"},
            ),
            final("approve", None, "Approved."),
            final("approve", None, "Approved anyway."),
            reflection("Denied. contractor cannot request a laptop."),
        ]
    )
    assert approved.decision == "deny"
    assert approved.reason_code == "ROLE_NOT_ELIGIBLE"
    assert approved.ticket_id is None

    escalated = _run(
        [
            action("get_employee_info", {"employee_id": "E9999"}),
            final("escalate", "VAGUE_REQUEST", "Please review this person."),
            final("escalate", "VAGUE_REQUEST", "Please review this person again."),
            reflection("Denied. No employee matches that id."),
        ]
    )
    assert escalated.decision == "deny"
    assert escalated.reason_code == "EMPLOYEE_NOT_FOUND"
    assert escalated.ticket_id is None
    assert "flag_for_human_review" not in {name for name, _args in escalated.tool_calls}


def test_reflection_revises_an_overcommit_and_confirms_a_faithful_draft() -> None:
    revised = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1003", "item": "laptop"},
            ),
            action(
                "flag_for_human_review",
                {
                    "employee_id": "E1003",
                    "request": "Please review the laptop.",
                    "reason": "WITHIN_WINDOW_WITH_REASON",
                },
            ),
            final("escalate", "WITHIN_WINDOW_WITH_REASON", ESCALATE_LAPTOP),
            reflection(
                f"{ESCALATE_LAPTOP} No delivery date is confirmed.",
                "revised",
                ["The draft promises a delivery that no observation confirms."],
            ),
        ],
        overcommit=True,
    )
    assert revised.reflection is not None
    assert revised.reflection["verdict"] == "revised"
    assert "will ship" not in str(revised.reflection["final_text"]).lower()
    assert "Draft (over-commit injected)" in revised.trace

    confirmed = _run(
        [
            action(
                "check_request_eligibility",
                {"employee_id": "E1001", "item": "monitor"},
            ),
            final("approve", None, APPROVE_TEXT),
            reflection(APPROVE_TEXT),
        ]
    )
    assert confirmed.reflection is not None
    assert confirmed.reflection["verdict"] == "confirmed"


def test_killed_server_reports_a_system_fault() -> None:
    async def _kill() -> RunResult:
        async with EquipmentSession(timeout=2) as session:
            specs = await session.list_tools()
            assert specs

            class _Drop:
                async def list_tools(self) -> list[dict]:
                    return specs

                async def call_tool(self, name: str, arguments: dict) -> dict:
                    kill_equipment_servers()
                    return await session.call_tool(name, arguments)

            return await handle_request(
                "Employee E1001 needs a monitor.",
                scripted(
                    [
                        action("get_employee_info", {"employee_id": "E1001"}),
                        action("get_employee_info", {"employee_id": "E1001"}),
                    ]
                ),
                session=_Drop(),
                max_tool_retries=1,
            )

    result = asyncio.run(_kill())
    assert result.decision == "system_fault"
    assert result.decision not in {"approve", "deny", "escalate"}
    assert result.ticket_id is None
    assert result.reflection is None
