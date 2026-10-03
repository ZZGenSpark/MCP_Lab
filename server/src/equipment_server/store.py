"""Review flags for one server process, optionally saved to a JSON file.

A new process starts empty unless ``EQUIPMENT_FLAG_STORE`` points at a file.
The host sets that variable so the next request can see tickets created earlier.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

OPEN_STATUS = "pending_review"
FLAG_STORE_ENV = "EQUIPMENT_FLAG_STORE"


@dataclass(frozen=True)
class FlagRecord:
    ticket_id: str
    employee_id: str
    item: str
    request: str
    reason: str
    status: str = OPEN_STATUS


class FlagStore:
    """Open flags. `create` does not check for duplicates.

    Pass a path to load tickets already saved by an earlier process and to
    write each new ticket back. Without a path the store stays in memory.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[FlagRecord] = []
        self._path = None if path is None or str(path).strip() == "" else Path(path)
        self._load()

    def reset(self) -> None:
        self._records.clear()
        self._save()

    def records(self) -> tuple[FlagRecord, ...]:
        return tuple(self._records)

    def has_open(self, employee_id: str, item: str) -> bool:
        return any(
            record.employee_id == employee_id
            and record.item == item
            and record.status == OPEN_STATUS
            for record in self._records
        )

    def create(
        self, employee_id: str, item: str, request: str, reason: str
    ) -> FlagRecord:
        record = FlagRecord(
            ticket_id=f"REV-{len(self._records) + 1:04d}",
            employee_id=employee_id,
            item=item,
            request=request,
            reason=reason,
        )
        self._records.append(record)
        self._save()
        return record

    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            return
        raw = self._path.read_text(encoding="utf-8").strip()
        if not raw:
            return
        data = json.loads(raw)
        if not isinstance(data, list):
            raise TypeError(f"flag store must be a JSON list: {self._path}")
        self._records = [_record(item) for item in data]

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(record) for record in self._records], indent=2)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(self._path)


def _record(item: object) -> FlagRecord:
    if not isinstance(item, dict):
        raise TypeError("flag store entries must be objects")
    return FlagRecord(
        ticket_id=str(item["ticket_id"]),
        employee_id=str(item["employee_id"]),
        item=str(item["item"]),
        request=str(item["request"]),
        reason=str(item["reason"]),
        status=str(item.get("status", OPEN_STATUS)),
    )


def open_flag_store() -> FlagStore:
    """Store for this process. A path in the environment reloads saved tickets."""
    raw = os.environ.get(FLAG_STORE_ENV, "").strip()
    return FlagStore(raw or None)


flag_store = open_flag_store()


def reset_store() -> None:
    flag_store.reset()
