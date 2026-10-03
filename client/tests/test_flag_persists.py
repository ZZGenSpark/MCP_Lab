"""A second server process sees a ticket saved by the first."""

from __future__ import annotations

import asyncio
import os

from equipment_client.session import EquipmentSession, server_parameters

REQUEST = "I need a monitor for my desk."
REASON = "The desk has no display for daily work."


def test_second_process_sees_the_open_ticket(tmp_path) -> None:
    path = tmp_path / "flags.json"
    env = os.environ.copy()
    env["EQUIPMENT_FLAG_STORE"] = str(path)
    params = server_parameters(env)
    created, duplicate, nxt = asyncio.run(_two_processes(params))
    assert created["ok"] is True
    assert created["ticket_id"] == "REV-0001"
    assert duplicate["ok"] is False
    assert duplicate["error"]["code"] == "DUPLICATE_FLAG"
    assert nxt["ticket_id"] == "REV-0002"

    fresh = asyncio.run(_one(EquipmentSession(timeout=5)))
    assert fresh["ticket_id"] == "REV-0001"


async def _two_processes(params) -> tuple[dict, dict, dict]:
    async with EquipmentSession(params, timeout=5) as first:
        created = await first.call_tool(
            "flag_for_human_review",
            {"employee_id": "E1001", "request": REQUEST, "reason": REASON},
        )
    async with EquipmentSession(params, timeout=5) as second:
        duplicate = await second.call_tool(
            "flag_for_human_review",
            {
                "employee_id": "E1001",
                "request": "Please review a monitor request.",
                "reason": REASON,
            },
        )
        nxt = await second.call_tool(
            "flag_for_human_review",
            {
                "employee_id": "E1001",
                "request": "I need a keyboard.",
                "reason": "The current keyboard is missing keys.",
            },
        )
    return created, duplicate, nxt


async def _one(session: EquipmentSession) -> dict:
    async with session:
        return await session.call_tool(
            "flag_for_human_review",
            {"employee_id": "E1001", "request": REQUEST, "reason": REASON},
        )
