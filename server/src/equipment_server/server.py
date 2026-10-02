"""MCP server. Registers the four equipment tools over stdio."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer

from equipment_server.tools import check_request_eligibility as eligibility
from equipment_server.tools import flag_for_human_review as flag_review
from equipment_server.tools import get_employee_info as employee_info
from equipment_server.tools import get_policy_limits as policy_limits
from equipment_server.validation import internal_error

server = MCPServer("equipment-server")


def _call(fn: Callable[..., dict[str, Any]], *args: object) -> dict[str, Any]:
    """Return a tool dict, or INTERNAL_ERROR if the tool raises."""
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001
        return internal_error()


@server.tool()
def get_employee_info(employee_id: str) -> dict[str, Any]:
    """Return role, tenure, and equipment on file for an employee id."""
    return _call(employee_info, employee_id)


@server.tool()
def get_policy_limits(role: str) -> dict[str, Any]:
    """Return eligible items and refresh limits for a role."""
    return _call(policy_limits, role)


@server.tool()
def check_request_eligibility(employee_id: str, item: str) -> dict[str, Any]:
    """Report whether one catalog item is inside policy. Does not decide."""
    return _call(eligibility, employee_id, item)


@server.tool()
def flag_for_human_review(
    employee_id: str, request: str, reason: str
) -> dict[str, Any]:
    """Open a review ticket after validation. Unknown ids create no ticket."""
    return _call(flag_review, employee_id, request, reason)


def run() -> None:
    """Serve tools over stdio until the client disconnects."""
    server.run(transport="stdio")
