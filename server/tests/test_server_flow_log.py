"""A tool call records the function, the checks, and the result."""

from __future__ import annotations

import equipment_server.server as server_module

import flowlog


def test_employee_lookup_writes_its_validations(tmp_path, monkeypatch) -> None:
    path = tmp_path / "run.log"
    monkeypatch.setenv(flowlog.ENV_PATH, str(path))
    result = server_module.get_employee_info("E1001")
    text = path.read_text(encoding="utf-8")
    assert result["ok"] is True
    assert "## 1  server.get_employee_info" in text
    assert "function:    get_employee_info" in text
    assert '"employee_id": "E1001"' in text
    assert "validate_employee_id(E1001) -> pass, role=standard" in text
    assert '"tenure_days": 2178' in text
