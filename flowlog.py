"""Readable flow log for one equipment run.

Host, client, and server append to the same file. Each step records the
function, the previous component's output, the validations that ran, and
this step's output. Nothing is written unless ``MCPLAB_FLOW_LOG`` is set
to a file path. ``begin`` sets that variable for the current process so a
stdio server child inherits it.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

ENV_PATH = "MCPLAB_FLOW_LOG"
ENV_POINTER = "MCPLAB_FLOW_LOG_POINTER"

_current: ContextVar[_Step | None] = ContextVar("flowlog_step", default=None)


class _Step:
    def __init__(self, component: str, function: str, previous: object) -> None:
        self.component = component
        self.function = function
        self.previous = previous
        self.validations: list[str] = []
        self.result: object = "(no output)"

    def set_output(self, value: object) -> None:
        self.result = value


class _Silent:
    def set_output(self, value: object) -> None:
        return None


def enabled() -> bool:
    """True when this process should append to a flow log."""
    return _active_path() is not None


def begin(directory: str, label: str, request: str) -> Path:
    """Create a new log, point MCPLAB_FLOW_LOG at it, and write the header."""
    path = _new_path(directory, label)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.environ[ENV_PATH] = str(path)
    _publish(path)
    when = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    header = (
        "IT equipment request — flow log\n"
        f"time:    {when}\n"
        "request:\n"
        f"{_show(request)}\n"
        "\n"
        "Read top to bottom. Each step is one function call.\n"
        "previous    what the previous component handed this function\n"
        "validations checks this function ran\n"
        "output      what this function returned\n"
    )
    with path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(header)
    return path


def record(
    component: str,
    function: str,
    previous: object,
    validations: list[str] | None,
    output: object,
) -> None:
    """Append one step. No-op when logging is off."""
    path = _active_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        number = handle.read().count("\n## ") + 1
        handle.write(_block(number, component, function, previous, validations, output))


def validation(message: str) -> None:
    """Attach a check to the server tool step that is currently running."""
    step = _current.get()
    if step is not None:
        step.validations.append(message)


@contextmanager
def span(component: str, function: str, previous: object) -> Iterator[_Step | _Silent]:
    """Record a function when the block exits, including nested validations."""
    if not enabled():
        yield _Silent()
        return
    step = _Step(component, function, previous)
    token = _current.set(step)
    try:
        yield step
    finally:
        _current.reset(token)
        record(component, function, previous, step.validations, step.result)


def _publish(path: Path) -> None:
    """Point a long-lived server at this log. The child inherited the pointer path."""
    pointer = os.environ.get(ENV_POINTER, "").strip()
    if not pointer:
        return
    target = Path(pointer)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(path.resolve()) + "\n", encoding="utf-8")


def _active_path() -> Path | None:
    followed = _follow_pointer()
    if followed is not None:
        return followed
    raw = os.environ.get(ENV_PATH, "").strip()
    if not raw:
        return None
    return Path(raw)


def _follow_pointer() -> Path | None:
    pointer = os.environ.get(ENV_POINTER, "").strip()
    if not pointer:
        return None
    file = Path(pointer)
    if not file.is_file():
        return None
    raw = file.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return Path(raw)


def _new_path(directory: str, label: str) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-").lower()
    slug = slug[:48] or "run"
    return Path(directory) / f"{stamp}-{slug}.log"


def _block(
    number: int,
    component: str,
    function: str,
    previous: object,
    validations: list[str] | None,
    output: object,
) -> str:
    title = f"{component}.{function}"
    checks = validations if validations else ["(none)"]
    check_text = "\n".join(f"  - {item}" for item in checks)
    return (
        f"\n## {number}  {title}\n"
        "\n"
        f"function:    {function}\n"
        "previous:\n"
        f"{_show(previous)}\n"
        "validations:\n"
        f"{check_text}\n"
        "output:\n"
        f"{_show(output)}\n"
    )


def _show(value: object) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, indent=2, default=str, ensure_ascii=False)
    if not text:
        return "  "
    return "\n".join(f"  {line}" for line in text.splitlines())
