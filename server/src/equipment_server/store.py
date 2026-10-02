"""In-memory review flags. Reset between tests."""

from __future__ import annotations

from dataclasses import dataclass

OPEN_STATUS = "pending_review"


@dataclass(frozen=True)
class FlagRecord:
    ticket_id: str
    employee_id: str
    item: str
    request: str
    reason: str
    status: str = OPEN_STATUS


class FlagStore:
    """Open flags for one process. `create` does not check for duplicates."""

    def __init__(self) -> None:
        self._records: list[FlagRecord] = []

    def reset(self) -> None:
        self._records.clear()

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
        return record


flag_store = FlagStore()


def reset_store() -> None:
    flag_store.reset()
