"""One stdio server for many requests, with tickets saved between processes."""

from __future__ import annotations

import os
from pathlib import Path

from equipment_client.session import (
    DEFAULT_TIMEOUT_SECONDS,
    EquipmentSession,
    server_parameters,
)
from mcp import StdioServerParameters

import config as root_config
import flowlog

FLAG_STORE_ENV = "EQUIPMENT_FLAG_STORE"


def flag_file() -> Path:
    """JSON file of open tickets. A later server process loads this."""
    cfg = root_config.load_config()
    return (Path(cfg.agent.logs_dir) / "flags.json").resolve()


def clear_saved_flags() -> None:
    """Start a demo from an empty ticket list."""
    path = flag_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]\n", encoding="utf-8")


def open_equipment_session(
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> EquipmentSession:
    """Launch the server with the saved flag file on its environment."""
    path = flag_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    base = server_parameters()
    env = dict(base.env or {})
    env[FLAG_STORE_ENV] = str(path)
    params = StdioServerParameters(
        command=base.command,
        args=list(base.args),
        env=env,
        cwd=base.cwd,
    )
    return EquipmentSession(params, timeout=timeout)


def use_flow_pointer() -> str:
    """Return the pointer path a long-lived server should follow."""
    cfg = root_config.load_config()
    pointer = (Path(cfg.agent.logs_dir) / ".current-flow-log").resolve()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    os.environ[flowlog.ENV_POINTER] = str(pointer)
    return str(pointer)
