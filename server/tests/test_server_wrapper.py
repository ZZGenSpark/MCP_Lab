"""The MCP wrapper turns an unexpected exception into INTERNAL_ERROR."""

from __future__ import annotations

import equipment_server.server as server_module


def test_unexpected_exception_returns_internal_error(monkeypatch) -> None:
    def boom(employee_id: str) -> dict[str, object]:
        raise RuntimeError(f"disk failed for {employee_id}")

    monkeypatch.setattr(server_module, "employee_info", boom)
    result = server_module.get_employee_info("E1001")
    assert result == {
        "ok": False,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Unexpected server error",
            "field": "server",
            "retryable": True,
            "hint": "Retry the call once. If it fails again, report a system fault.",
        },
    }
