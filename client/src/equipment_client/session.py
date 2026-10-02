"""Stdio session: connect, list tools, and call a tool into a plain dict."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import config


def server_parameters(
    env: Mapping[str, str] | None = None,
) -> StdioServerParameters:
    """Launch command from root config, with the server package on PYTHONPATH."""
    cfg = config.load_config(env)
    root = Path(config.__file__).resolve().parent
    source = os.environ if env is None else env
    pythonpath = os.pathsep.join(
        part
        for part in (
            str(root / "server" / "src"),
            str(root),
            source.get("PYTHONPATH", ""),
        )
        if part
    )
    child_env = dict(source)
    child_env["PYTHONPATH"] = pythonpath
    return StdioServerParameters(
        command=cfg.server.command,
        args=list(cfg.server.args),
        env=child_env,
        cwd=str(root),
    )


def parse_tool_result(result: object) -> dict[str, Any]:
    """Read a tool result as the dict the server function returned."""
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    content = getattr(result, "content", None) or []
    text = "".join(
        block.text for block in content if getattr(block, "text", None) is not None
    )
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError("tool result must be a JSON object")
    return parsed


class EquipmentSession:
    """One stdio connection to the equipment server."""

    def __init__(self, params: StdioServerParameters | None = None) -> None:
        self._params = server_parameters() if params is None else params
        self._client: Any = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> Self:
        self._client = stdio_client(self._params)
        read, write = await self._client.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session is not None:
            await self._session.__aexit__(*exc)
        if self._client is not None:
            await self._client.__aexit__(*exc)

    async def list_tools(self) -> list[str]:
        session = self._require_session()
        listed = await session.list_tools()
        return [tool.name for tool in listed.tools]

    async def call_tool(
        self, name: str, arguments: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        session = self._require_session()
        result = await session.call_tool(name, dict(arguments or {}))
        return parse_tool_result(result)

    def _require_session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("session is not open")
        return self._session
