"""MCP server. This step exposes get_employee_info over stdio."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from equipment_server.tools import get_employee_info as employee_info

server = MCPServer("equipment-server")


@server.tool()
def get_employee_info(employee_id: str) -> dict[str, Any]:
    """Return role, tenure, and equipment on file for an employee id."""
    return employee_info(employee_id)


def run() -> None:
    """Serve tools over stdio until the client disconnects."""
    server.run(transport="stdio")
