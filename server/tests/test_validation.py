"""Error contract for shared validators. Each failure is a real rejected input."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

import pytest
from equipment_server.loaders import (
    Directory,
    PolicyData,
    load_employees,
    load_policies,
)
from equipment_server.store import FlagStore
from equipment_server.validation import (
    ERROR_CODES,
    ValidatedFlag,
    internal_error,
    policy_roles,
    tool_error,
    validate_employee_id,
    validate_flag_request,
    validate_item,
    validate_reason,
    validate_request_text,
    validate_role,
)

Invoke = Callable[[Directory, PolicyData, FlagStore], dict[str, Any]]


class Case(NamedTuple):
    name: str
    invoke: Invoke
    code: str
    field: str
    retryable: bool
    prime_store: bool = False


def _flag(
    employee_id: object,
    request: object,
    reason: object,
) -> Invoke:
    def invoke(
        directory: Directory, policies: PolicyData, store: FlagStore
    ) -> dict[str, Any]:
        result = validate_flag_request(
            employee_id,
            request,
            reason,
            directory=directory,
            policies=policies,
            store=store,
        )
        assert isinstance(result, dict)
        return result

    return invoke


CASES = [
    Case(
        "missing employee",
        _flag("E9999", "I need a monitor", "I need a monitor for my desk."),
        "EMPLOYEE_NOT_FOUND",
        "employee_id",
        False,
    ),
    Case(
        "malformed id",
        _flag("abc", "I need a monitor", "I need a monitor for my desk."),
        "INVALID_ARGUMENT",
        "employee_id",
        True,
    ),
    Case(
        "lowercase id",
        _flag("e0001", "I need a monitor", "I need a monitor for my desk."),
        "INVALID_ARGUMENT",
        "employee_id",
        True,
    ),
    Case(
        "id is none",
        _flag(None, "I need a monitor", "I need a monitor for my desk."),
        "INVALID_ARGUMENT",
        "employee_id",
        True,
    ),
    Case(
        "empty request",
        _flag("E1001", "   ", "I need a monitor for my desk."),
        "INVALID_ARGUMENT",
        "request",
        True,
    ),
    Case(
        "request too long",
        _flag("E1001", "m" * 501, "I need a monitor for my desk."),
        "INVALID_ARGUMENT",
        "request",
        True,
    ),
    Case(
        "unknown item in request",
        _flag("E1001", "I need a standing desk", "I need a monitor for my desk."),
        "UNKNOWN_ITEM",
        "request",
        False,
    ),
    Case(
        "short reason",
        _flag("E1001", "I need a monitor", "Help"),
        "INVALID_ARGUMENT",
        "reason",
        True,
    ),
    Case(
        "duplicate flag",
        _flag("E1001", "I need a monitor", "I need a monitor for my desk."),
        "DUPLICATE_FLAG",
        "item",
        False,
        True,
    ),
]


@pytest.fixture
def directory() -> Directory:
    return load_employees()


@pytest.fixture
def policies() -> PolicyData:
    return load_policies()


@pytest.fixture
def store() -> FlagStore:
    return FlagStore()


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_error_contract(
    case: Case, directory: Directory, policies: PolicyData, store: FlagStore
) -> None:
    if case.prime_store:
        store.create(
            "E1001", "monitor", "I need a monitor", "I need a monitor for my desk."
        )
    result = case.invoke(directory, policies, store)
    assert set(result) == {"ok", "error"}
    assert result["ok"] is False
    error = result["error"]
    assert set(error) == {"code", "message", "field", "retryable", "hint"}
    assert error["code"] in ERROR_CODES
    assert error["code"] == case.code
    assert error["field"] == case.field
    assert error["retryable"] is case.retryable
    assert error["message"]
    assert error["hint"]
    if case.prime_store:
        assert len(store.records()) == 1
    else:
        assert store.records() == ()


def test_documented_error_codes() -> None:
    assert ERROR_CODES == {
        "INVALID_ARGUMENT",
        "EMPLOYEE_NOT_FOUND",
        "UNKNOWN_ROLE",
        "UNKNOWN_ITEM",
        "DUPLICATE_FLAG",
        "INTERNAL_ERROR",
    }


def test_missing_employee_matches_schema_example(directory: Directory) -> None:
    result = validate_employee_id("E9999", directory)
    assert isinstance(result, dict)
    assert result["error"] == {
        "code": "EMPLOYEE_NOT_FOUND",
        "message": "No employee with id E9999",
        "field": "employee_id",
        "retryable": False,
        "hint": "Check the id format E#### or ask the requester to confirm.",
    }


def test_unknown_role_and_item(policies: PolicyData) -> None:
    role = validate_role("boss", policy_roles(policies))
    item = validate_item("standing desk", policies.catalog)
    assert isinstance(role, dict)
    assert isinstance(item, dict)
    assert role["error"]["code"] == "UNKNOWN_ROLE"
    assert role["error"]["retryable"] is False
    assert item["error"]["code"] == "UNKNOWN_ITEM"
    assert item["error"]["hint"] == "Requestable items: " + ", ".join(policies.catalog)


def test_internal_error_is_retryable() -> None:
    result = internal_error()
    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert result["error"]["retryable"] is True
    assert result["error"]["field"] == "server"


def test_tool_error_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="code"):
        tool_error("NOT_A_CODE", "message", "field", hint="hint")


def test_flag_chain_stops_at_the_first_failure(
    directory: Directory, policies: PolicyData, store: FlagStore
) -> None:
    store.create(
        "E1001", "monitor", "I need a monitor", "I need a monitor for my desk."
    )
    result = validate_flag_request(
        "E9999",
        "standing desk",
        "no",
        directory=directory,
        policies=policies,
        store=store,
    )
    assert isinstance(result, dict)
    assert result["error"]["code"] == "EMPLOYEE_NOT_FOUND"
    assert len(store.records()) == 1

    item_result = validate_flag_request(
        "E1001",
        "standing desk",
        "no",
        directory=directory,
        policies=policies,
        store=store,
    )
    assert isinstance(item_result, dict)
    assert item_result["error"]["code"] == "UNKNOWN_ITEM"


def test_valid_flag_request_does_not_create_a_ticket(
    directory: Directory, policies: PolicyData, store: FlagStore
) -> None:
    result = validate_flag_request(
        " E1001 ",
        "I need a Monitor for my desk.",
        "DATA_CONFLICT",
        directory=directory,
        policies=policies,
        store=store,
    )
    assert isinstance(result, ValidatedFlag)
    assert result.employee_id == "E1001"
    assert result.item == "monitor"
    assert result.reason == "DATA_CONFLICT"
    assert store.records() == ()


def test_role_and_item_are_normalized(policies: PolicyData) -> None:
    assert validate_role("  Manager ", policy_roles(policies)) == "manager"
    assert validate_item(" Laptop ", policies.catalog) == "laptop"


def test_request_and_reason_bounds() -> None:
    assert validate_request_text("  keyboard  ") == "keyboard"
    assert validate_reason("1234567890") == "1234567890"
    short = validate_reason("123456789")
    assert isinstance(short, dict)
    assert short["error"]["code"] == "INVALID_ARGUMENT"


def test_ticket_ids_increment_and_reset() -> None:
    store = FlagStore()
    first = store.create(
        "E1001", "monitor", "I need a monitor", "Desk has no screen yet."
    )
    second = store.create(
        "E1001", "laptop", "I need a laptop", "Current laptop will not boot."
    )
    assert first.ticket_id == "REV-0001"
    assert second.ticket_id == "REV-0002"
    assert store.has_open("E1001", "monitor")
    assert store.has_open("E1001", "laptop")
    store.reset()
    assert store.records() == ()
    assert store.has_open("E1001", "monitor") is False
