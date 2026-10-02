"""Full-stack tests open a new server process, so the flag store starts empty."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from equipment_host.llm import ScriptedLLM


def scripted(replies: list[str]) -> ScriptedLLM:
    return ScriptedLLM(replies)


def kill_equipment_servers() -> None:
    """Stop equipment_server subprocesses started by this test run."""
    if Path("/proc").is_dir():
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                command = Path(f"/proc/{name}/cmdline").read_bytes()
            except OSError:
                continue
            if b"equipment_server" in command:
                os.kill(int(name), signal.SIGKILL)
        return
    listing = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
    for line in listing.splitlines():
        if "equipment_server" not in line:
            continue
        pid = int(line.split(None, 1)[0])
        os.kill(pid, signal.SIGKILL)
