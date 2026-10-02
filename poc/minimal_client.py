"""Minimal MCP client. Launches poc/minimal_server.py over stdio and calls ping."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).with_name("minimal_server.py")


def _tool_text(result: object) -> str:
    content = getattr(result, "content", None)
    if not content:
        return str(result)
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "".join(parts)


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        init = await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("ping")
        print(f"server: {init.server_info.name}")
        print(f"protocol: {init.protocol_version}")
        print("tools:")
        for tool in tools.tools:
            print(f"- {tool.name}: {tool.description}")
        print(f"call ping -> {_tool_text(result)}")


if __name__ == "__main__":
    asyncio.run(main())
