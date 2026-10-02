"""Argument checks and the structured tool-error envelope.

Validators return a ToolError dict, or a value when the argument is usable.
They do not write to the flag store. `flag_for_human_review` runs the checks
in order and stops at the first failure, before any ticket is created.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

from equipment_server.loaders import (
    EMPLOYEE_ID,
    Directory,
    Employee,
    PolicyData,
    load_employees,
    load_policies,
)
from equipment_server.store import FlagStore, flag_store

ERROR_CODES = frozenset(
    {
        "INVALID_ARGUMENT",
        "EMPLOYEE_NOT_FOUND",
        "UNKNOWN_ROLE",
        "UNKNOWN_ITEM",
        "DUPLICATE_FLAG",
        "INTERNAL_ERROR",
    }
)
RETRYABLE_CODES = frozenset({"INVALID_ARGUMENT", "INTERNAL_ERROR"})
REASON_CODES = frozenset(
    {
        "WITHIN_WINDOW_WITH_REASON",
        "TENURE_UNDER_90_DAYS",
        "DATA_CONFLICT",
        "VAGUE_REQUEST",
    }
)
REQUEST_MAX_LENGTH = 500
REASON_MIN_LENGTH = 10

_EMPLOYEE_HINT = "Check the id format E#### or ask the requester to confirm."
_ID_HINT = "Use an employee id like E1001: uppercase E and four digits."


@dataclass(frozen=True)
class ToolError:
    code: str
    message: str
    field: str
    retryable: bool
    hint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "field": self.field,
                "retryable": self.retryable,
                "hint": self.hint,
            },
        }


@dataclass(frozen=True)
class ValidatedFlag:
    employee_id: str
    item: str
    request: str
    reason: str


def tool_error(code: str, message: str, field: str, hint: str) -> dict[str, Any]:
    """Build the envelope every failing tool returns."""
    if code not in ERROR_CODES:
        raise ValueError(f"unknown error code: {code}")
    if not message or not field or not hint:
        raise ValueError("message, field, and hint must be non-empty")
    return ToolError(
        code=code,
        message=message,
        field=field,
        retryable=code in RETRYABLE_CODES,
        hint=hint,
    ).as_dict()


def internal_error(message: str = "Unexpected server error") -> dict[str, Any]:
    return tool_error(
        "INTERNAL_ERROR",
        message,
        "server",
        hint="Retry the call once. If it fails again, report a system fault.",
    )


def validate_employee_id(
    employee_id: object, directory: Directory
) -> Employee | dict[str, Any]:
    if not isinstance(employee_id, str):
        return tool_error(
            "INVALID_ARGUMENT",
            "employee_id must be a string like E1001",
            "employee_id",
            hint=_ID_HINT,
        )
    normalized = employee_id.strip()
    if EMPLOYEE_ID.fullmatch(normalized) is None:
        return tool_error(
            "INVALID_ARGUMENT",
            f"employee_id {employee_id!r} does not match E####",
            "employee_id",
            hint=_ID_HINT,
        )
    employee = directory.by_id().get(normalized)
    if employee is None:
        return tool_error(
            "EMPLOYEE_NOT_FOUND",
            f"No employee with id {normalized}",
            "employee_id",
            hint=_EMPLOYEE_HINT,
        )
    return employee


def validate_role(role: object, roles: Collection[str]) -> str | dict[str, Any]:
    allowed = tuple(roles)
    if not isinstance(role, str) or not role.strip():
        return tool_error(
            "INVALID_ARGUMENT",
            "role must be a non-empty string",
            "role",
            hint=_role_hint(allowed),
        )
    normalized = role.strip().lower()
    if normalized not in {name.lower() for name in allowed}:
        return tool_error(
            "UNKNOWN_ROLE",
            f"Unknown role {normalized!r}",
            "role",
            hint=_role_hint(allowed),
        )
    return normalized


def validate_item(item: object, catalog: Sequence[str]) -> str | dict[str, Any]:
    if not isinstance(item, str) or not item.strip():
        return tool_error(
            "INVALID_ARGUMENT",
            "item must be a non-empty string",
            "item",
            hint=_catalog_hint(catalog),
        )
    normalized = item.strip().lower()
    if normalized not in {name.lower() for name in catalog}:
        return tool_error(
            "UNKNOWN_ITEM",
            f"Unknown item {normalized!r}",
            "item",
            hint=_catalog_hint(catalog),
        )
    return normalized


def validate_request_text(request: object) -> str | dict[str, Any]:
    if not isinstance(request, str) or not request.strip():
        return tool_error(
            "INVALID_ARGUMENT",
            "request must be a non-empty string",
            "request",
            hint=f"Describe the item in at most {REQUEST_MAX_LENGTH} characters.",
        )
    text = request.strip()
    if len(text) > REQUEST_MAX_LENGTH:
        return tool_error(
            "INVALID_ARGUMENT",
            f"request is longer than {REQUEST_MAX_LENGTH} characters",
            "request",
            hint=f"Keep the request within {REQUEST_MAX_LENGTH} characters.",
        )
    return text


def validate_reason(reason: object) -> str | dict[str, Any]:
    if not isinstance(reason, str) or not reason.strip():
        return tool_error(
            "INVALID_ARGUMENT",
            "reason must be a non-empty string",
            "reason",
            hint=_reason_hint(),
        )
    text = reason.strip()
    if text in REASON_CODES or len(text) >= REASON_MIN_LENGTH:
        return text
    return tool_error(
        "INVALID_ARGUMENT",
        "reason must be at least 10 characters or a known reason code",
        "reason",
        hint=_reason_hint(),
    )


def validate_not_duplicate(
    employee_id: str, item: str, store: FlagStore
) -> dict[str, Any] | None:
    if store.has_open(employee_id, item):
        return tool_error(
            "DUPLICATE_FLAG",
            f"Open review already exists for {employee_id} {item}",
            "item",
            hint="Use the existing ticket instead of flagging the same item again.",
        )
    return None


def validate_flag_request(
    employee_id: object,
    request: object,
    reason: object,
    *,
    directory: Directory | None = None,
    policies: PolicyData | None = None,
    store: FlagStore | None = None,
) -> ValidatedFlag | dict[str, Any]:
    """Run the flag checks in order. Return the first error, or the parsed request.

    The store is only read. A passing result does not create a ticket.
    """
    directory = load_employees() if directory is None else directory
    policies = load_policies() if policies is None else policies
    store = flag_store if store is None else store

    employee = validate_employee_id(employee_id, directory)
    if isinstance(employee, dict):
        return employee

    request_text = validate_request_text(request)
    if isinstance(request_text, dict):
        return request_text
    found = _catalog_items_in(request_text, policies.catalog)
    if not found:
        return tool_error(
            "UNKNOWN_ITEM",
            "request does not name a catalog item",
            "request",
            hint=_catalog_hint(policies.catalog),
        )
    if len(found) > 1:
        return tool_error(
            "INVALID_ARGUMENT",
            "request must name one catalog item",
            "request",
            hint=_catalog_hint(policies.catalog),
        )

    reason_text = validate_reason(reason)
    if isinstance(reason_text, dict):
        return reason_text

    duplicate = validate_not_duplicate(employee.employee_id, found[0], store)
    if duplicate is not None:
        return duplicate
    return ValidatedFlag(
        employee_id=employee.employee_id,
        item=found[0],
        request=request_text,
        reason=reason_text,
    )


def policy_roles(policies: PolicyData) -> tuple[str, ...]:
    seen: list[str] = []
    for limit in policies.limits:
        if limit.role not in seen:
            seen.append(limit.role)
    return tuple(seen)


def _catalog_items_in(text: str, catalog: Sequence[str]) -> list[str]:
    found: list[str] = []
    for item in catalog:
        if re.search(rf"\b{re.escape(item)}\b", text, flags=re.IGNORECASE):
            found.append(item)
    return found


def _catalog_hint(catalog: Sequence[str]) -> str:
    return "Requestable items: " + ", ".join(catalog)


def _role_hint(roles: Sequence[str]) -> str:
    return "Use one of: " + ", ".join(roles)


def _reason_hint() -> str:
    return "Use at least 10 characters, or one of: " + ", ".join(sorted(REASON_CODES))
