"""MCP server. Registers the four equipment tools over stdio."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer

import flowlog
from equipment_server.tools import check_request_eligibility as eligibility
from equipment_server.tools import flag_for_human_review as flag_review
from equipment_server.tools import get_employee_info as employee_info
from equipment_server.tools import get_policy_limits as policy_limits
from equipment_server.validation import internal_error

server = MCPServer("equipment-server")


def _call(fn: Callable[..., dict[str, Any]], **arguments: object) -> dict[str, Any]:
    """Return a tool dict, or INTERNAL_ERROR if the tool raises."""
    with flowlog.span("server", fn.__name__, arguments) as step:
        try:
            result = fn(**arguments)
        except Exception:  # noqa: BLE001
            result = internal_error()
        step.set_output(result)
        return result


@server.tool()
def get_employee_info(employee_id: str) -> dict[str, Any]:
    """Return role, tenure, and equipment on file for an employee id."""
    return _call(employee_info, employee_id=employee_id)


@server.tool()
def get_policy_limits(role: str) -> dict[str, Any]:
    """Return eligible items and refresh limits for a role."""
    return _call(policy_limits, role=role)


@server.tool()
def check_request_eligibility(
    employee_id: str, item: str, reason: str | None = None
) -> dict[str, Any]:
    """Report whether one catalog item is inside policy. Does not decide.

    Pass the requester's own words in reason. Pass an empty item when the
    request names no item. eligible is true, false, or "unclear"; unclear
    means a person must review it.
    """
    return _call(eligibility, employee_id=employee_id, item=item, reason=reason)


@server.tool()
def flag_for_human_review(
    employee_id: str, request: str, reason: str
) -> dict[str, Any]:
    """Open a review ticket after validation. Unknown ids create no ticket."""
    return _call(flag_review, employee_id=employee_id, request=request, reason=reason)


def run() -> None:
    """Serve tools over stdio until the client disconnects."""
    server.run(transport="stdio")
