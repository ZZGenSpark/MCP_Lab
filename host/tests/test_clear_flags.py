"""The clear command empties the saved ticket file."""

from __future__ import annotations

from equipment_host.clear_flags import main


def test_main_replaces_saved_tickets_with_an_empty_list(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("MCPLAB_AGENT_LOGS_DIR", str(tmp_path))
    path = tmp_path / "flags.json"
    path.write_text('[{"ticket_id": "REV-0001"}]\n', encoding="utf-8")
    main()
    assert path.read_text(encoding="utf-8") == "[]\n"
    assert f"cleared: {path.resolve()}" in capsys.readouterr().out
