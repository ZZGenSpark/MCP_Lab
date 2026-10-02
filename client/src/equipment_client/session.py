"""Stdio session: connect, list tools, and call a tool into a plain dict."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import config

DEFAULT_TIMEOUT_SECONDS = 30.0
_TRANSPORT_HINT = "Retry the call once. If it fails again, report a system fault."


def transport_error(message: str) -> dict[str, Any]:
    """One error shape for a dropped connection, a timeout, or isError."""
    return {
        "ok": False,
        "error": {
            "code": "TRANSPORT_ERROR",
            "message": message,
            "field": "transport",
            "retryable": True,
            "hint": _TRANSPORT_HINT,
        },
    }


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


def normalize_tool_result(result: object) -> dict[str, Any]:
    """Return the tool dict, or TRANSPORT_ERROR when the call did not."""
    is_error = bool(
        getattr(result, "is_error", False) or getattr(result, "isError", False)
    )
    try:
        parsed = parse_tool_result(result)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict) and "ok" in parsed:
        return parsed
    if is_error:
        return transport_error("The server marked the tool call as an error")
    return transport_error("The tool result was not a JSON object")


class EquipmentSession:
    """One stdio connection to the equipment server."""

    def __init__(
        self,
        params: StdioServerParameters | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._params = server_parameters() if params is None else params
        self._timeout = timeout
        self._client: Any = None
        self._session: ClientSession | None = None
        self._connect_error: dict[str, Any] | None = None

    async def __aenter__(self) -> Self:
        try:
            self._client = stdio_client(self._params)
            read, write = await self._client.__aenter__()
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await asyncio.wait_for(self._session.initialize(), timeout=self._timeout)
        except Exception as exc:  # noqa: BLE001
            self._connect_error = transport_error(f"Could not start the server: {exc}")
            await self._close_quietly()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._close_quietly()

    async def list_tools(self) -> list[dict[str, Any]]:
        """Tool name, description, and input schema from the live server."""
        if self._connect_error is not None:
            return []
        session = self._require_session()
        listed = await asyncio.wait_for(session.list_tools(), timeout=self._timeout)
        specs: list[dict[str, Any]] = []
        for tool in listed.tools:
            schema = getattr(tool, "input_schema", None)
            if schema is None:
                schema = getattr(tool, "inputSchema", {})
            specs.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": schema,
                }
            )
        return specs

    async def call_tool(
        self, name: str, arguments: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        if self._connect_error is not None:
            return self._connect_error
        session = self._require_session()
        try:
            result = await asyncio.wait_for(
                session.call_tool(name, dict(arguments or {})),
                timeout=self._timeout,
            )
        except TimeoutError:
            return transport_error(f"Tool call {name} timed out")
        except Exception as exc:  # noqa: BLE001
            return transport_error(f"Tool call {name} failed: {exc}")
        return normalize_tool_result(result)

    def _require_session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("session is not open")
        return self._session

    async def _close_quietly(self) -> None:
        self._shutdown_error = None
        for closer in (self._session, self._client):
            if closer is None:
                continue
            try:
                await closer.__aexit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                self._shutdown_error = str(exc)
        self._session = None
        self._client = None
