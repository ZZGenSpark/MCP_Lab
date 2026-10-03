"""Flow log formatting. Steps stay quiet unless a path is set."""

from __future__ import annotations

import flowlog


def test_record_is_quiet_without_a_path(monkeypatch) -> None:
    monkeypatch.delenv(flowlog.ENV_PATH, raising=False)
    monkeypatch.delenv(flowlog.ENV_POINTER, raising=False)
    flowlog.record("host", "llm.complete", "in", None, "out")
    flowlog.validation("should not attach")


def test_begin_numbers_steps_in_order(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(flowlog.ENV_PATH, raising=False)
    monkeypatch.delenv(flowlog.ENV_POINTER, raising=False)
    path = flowlog.begin(str(tmp_path), "Employee E1001 monitor", "Need a monitor")
    flowlog.record(
        "host",
        "llm.complete",
        "Need a monitor",
        None,
        "Action: get_employee_info",
    )
    with flowlog.span("server", "get_employee_info", {"employee_id": "E1001"}) as step:
        flowlog.validation("validate_employee_id(E1001) -> pass")
        step.set_output({"ok": True, "employee_id": "E1001"})
    text = path.read_text(encoding="utf-8")
    assert "Need a monitor" in text
    assert "## 1  host.llm.complete" in text
    assert "previous:" in text
    assert "## 2  server.get_employee_info" in text
    assert "validate_employee_id(E1001) -> pass" in text
    assert '"ok": true' in text
    assert path.parent == tmp_path


def test_pointer_sends_the_next_step_to_the_new_log(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(flowlog.ENV_PATH, raising=False)
    monkeypatch.setenv(flowlog.ENV_POINTER, str(tmp_path / "pointer"))
    first = flowlog.begin(str(tmp_path), "one", "first request")
    flowlog.record("host", "llm.complete", "first", None, "kept on the first log")
    second = flowlog.begin(str(tmp_path), "two", "second request")
    flowlog.record(
        "server", "flag_for_human_review", "flag", None, "kept on the second log"
    )
    assert "kept on the first log" in first.read_text(encoding="utf-8")
    assert "kept on the second log" in second.read_text(encoding="utf-8")
    assert "kept on the second log" not in first.read_text(encoding="utf-8")
