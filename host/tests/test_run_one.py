"""Command-line parsing for a single request."""

from __future__ import annotations

import pytest
from equipment_host.run_one import parse_args


def test_joins_question_words() -> None:
    args = parse_args(["Employee", "E1001", "asks", "for", "a", "monitor."])
    assert " ".join(args.question) == "Employee E1001 asks for a monitor."


def test_requires_a_question() -> None:
    with pytest.raises(SystemExit):
        parse_args([])
