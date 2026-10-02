"""Parsing and transport errors, without a live server."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from equipment_client.session import (
    EquipmentSession,
    normalize_tool_result,
    parse_tool_result,
    server_parameters,
    transport_error,
)
from mcp import StdioServerParameters


def test_parse_tool_result_reads_text_content() -> None:
    payload = {"ok": True, "employee_id": "E1001"}
    result = SimpleNamespace(
        structured_content=None,
        content=[SimpleNamespace(text=json.dumps(payload))],
        is_error=False,
    )
    assert parse_tool_result(result) == payload


def test_parse_tool_result_prefers_structured_content() -> None:
    result = SimpleNamespace(
        structured_content={"ok": True, "role": "standard"},
        content=[SimpleNamespace(text="ignored")],
    )
    assert parse_tool_result(result)["role"] == "standard"


def test_is_error_without_an_envelope_is_transport_error() -> None:
    result = SimpleNamespace(
        structured_content=None,
        content=[SimpleNamespace(text="boom")],
        is_error=True,
    )
    normalized = normalize_tool_result(result)
    assert normalized["ok"] is False
    assert normalized["error"]["code"] == "TRANSPORT_ERROR"
    assert normalized["error"]["retryable"] is True
    assert normalized["error"]["field"] == "transport"


def test_is_error_keeps_a_structured_tool_error() -> None:
    envelope = transport_error("already structured")
    envelope["error"]["code"] = "INTERNAL_ERROR"
    result = SimpleNamespace(
        structured_content=envelope,
        content=[],
        is_error=True,
    )
    assert normalize_tool_result(result)["error"]["code"] == "INTERNAL_ERROR"


def test_server_parameters_use_the_config_command() -> None:
    params = server_parameters({"MCPLAB_SERVER_COMMAND": "python3", "PATH": "/usr/bin"})
    assert params.command == "python3"
    assert params.args == ["-m", "equipment_server"]
    assert "server/src" in params.env["PYTHONPATH"]


def test_call_tool_timeout_is_transport_error() -> None:
    session = EquipmentSession(
        StdioServerParameters(command="python3", args=["-c", ""]),
        timeout=0.05,
    )

    class Slow:
        async def call_tool(self, name: str, arguments: dict) -> object:
            await asyncio.sleep(1)
            return SimpleNamespace(is_error=False, content=[], structured_content={})

    session._session = Slow()  # type: ignore[assignment]
    result = asyncio.run(session.call_tool("get_employee_info", {}))
    assert result["error"]["code"] == "TRANSPORT_ERROR"
    assert "timed out" in result["error"]["message"]


def test_bad_launch_command_is_transport_error() -> None:
    params = StdioServerParameters(command="no-such-binary-mcplab", args=[])

    async def _open() -> dict:
        async with EquipmentSession(params, timeout=2) as session:
            return await session.call_tool(
                "get_employee_info", {"employee_id": "E1001"}
            )

    result = asyncio.run(_open())
    assert result["ok"] is False
    assert result["error"]["code"] == "TRANSPORT_ERROR"
    assert result["error"]["retryable"] is True


def test_parse_rejects_a_json_list() -> None:
    result = SimpleNamespace(
        structured_content=None,
        content=[SimpleNamespace(text="[1]")],
    )
    with pytest.raises(TypeError):
        parse_tool_result(result)
