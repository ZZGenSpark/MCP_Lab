"""A new FlagStore reloads tickets written by an earlier one."""

from __future__ import annotations

from equipment_server.store import FlagStore


def test_second_store_sees_the_saved_ticket(tmp_path) -> None:
    path = tmp_path / "flags.json"
    first = FlagStore(path)
    created = first.create(
        "E1001",
        "monitor",
        "I need a monitor for my desk.",
        "The desk has no display for daily work.",
    )
    assert created.ticket_id == "REV-0001"

    second = FlagStore(path)
    assert second.has_open("E1001", "monitor")
    assert second.records()[0].ticket_id == "REV-0001"
    follow = second.create(
        "E1001",
        "keyboard",
        "I need a keyboard.",
        "The current keyboard is missing keys.",
    )
    assert follow.ticket_id == "REV-0002"
    assert len(FlagStore(path).records()) == 2


def test_missing_file_starts_empty(tmp_path) -> None:
    store = FlagStore(tmp_path / "missing.json")
    assert store.records() == ()


def test_reset_clears_the_file(tmp_path) -> None:
    path = tmp_path / "flags.json"
    store = FlagStore(path)
    store.create("E1001", "monitor", "I need a monitor.", "Daily work needs a display.")
    store.reset()
    assert FlagStore(path).records() == ()
