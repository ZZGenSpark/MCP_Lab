"""Call every tool on the real server and compare it to the plain function."""

from __future__ import annotations

import asyncio

from equipment_client.session import EquipmentSession
from equipment_server.store import FlagStore
from equipment_server.tools import (
    check_request_eligibility,
    flag_for_human_review,
    get_employee_info,
    get_policy_limits,
)

TOOL_NAMES = (
    "get_employee_info",
    "get_policy_limits",
    "check_request_eligibility",
    "flag_for_human_review",
)


def test_stdio_tools_match_the_plain_functions() -> None:
    asyncio.run(_call())


async def _call() -> None:
    async with EquipmentSession() as session:
        specs = await session.list_tools()
        assert {spec["name"] for spec in specs} == set(TOOL_NAMES)
        for spec in specs:
            assert spec["description"]
            assert "properties" in spec["input_schema"]

        for employee_id in ("E1001", "E1003", "E9999"):
            over_stdio = await session.call_tool(
                "get_employee_info", {"employee_id": employee_id}
            )
            assert over_stdio == get_employee_info(employee_id)

        for role in ("standard", " Manager ", "boss", ""):
            over_stdio = await session.call_tool("get_policy_limits", {"role": role})
            assert over_stdio == get_policy_limits(role)

        pairs = (("E1001", "monitor"), ("E1002", "laptop"), ("E1001", "standing desk"))
        for employee_id, item in pairs:
            over_stdio = await session.call_tool(
                "check_request_eligibility",
                {"employee_id": employee_id, "item": item},
            )
            assert over_stdio == check_request_eligibility(employee_id, item)

        store = FlagStore()
        arguments = {
            "employee_id": "E1001",
            "request": "I need a monitor for my desk.",
            "reason": "The desk has no display for daily work.",
        }
        over_stdio = await session.call_tool("flag_for_human_review", arguments)
        local = flag_for_human_review(
            arguments["employee_id"],
            arguments["request"],
            arguments["reason"],
            store=store,
        )
        assert over_stdio == local
        assert over_stdio["ticket_id"] == "REV-0001"
