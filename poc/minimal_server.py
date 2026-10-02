"""One-tool MCP server used to prove a stdio connection.

The Python MCP SDK 2.x names this server class MCPServer.
"""

from mcp.server.mcpserver import MCPServer

server = MCPServer("equipment-poc")


@server.tool()
def ping() -> str:
    """Return pong so a client can prove the stdio connection."""
    return "pong"


if __name__ == "__main__":
    server.run(transport="stdio")
