"""Call get_employee_info on the real server over stdio."""

from __future__ import annotations

import asyncio

from equipment_client.session import EquipmentSession
from equipment_server.tools import get_employee_info


def test_get_employee_info_matches_the_plain_function() -> None:
    asyncio.run(_call())


async def _call() -> None:
    async with EquipmentSession() as session:
        assert await session.list_tools() == ["get_employee_info"]
        for employee_id in ("E1001", "E1003", "E9999"):
            over_stdio = await session.call_tool(
                "get_employee_info", {"employee_id": employee_id}
            )
            assert over_stdio == get_employee_info(employee_id)
