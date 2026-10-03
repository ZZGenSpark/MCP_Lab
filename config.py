"""Central configuration for the MCP IT Equipment Lab.

Defaults live here. Any value can be overridden with an environment variable
named MCPLAB_<SECTION>_<FIELD>, e.g. MCPLAB_LLM_MODEL=mistral.
Use `load_config()` to get a validated, immutable `Config`.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from typing import Any

ENV_PREFIX = "MCPLAB_"


@dataclass(frozen=True)
class ServerConfig:
    command: str = sys.executable
    args: tuple[str, ...] = ("-m", "equipment_server")


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = "http://localhost:11434"
    model: str = "qwen3:8b"
    fallback_model: str = "mistral"
    temperature: float = 0.0
    timeout_seconds: int = 120
    # Qwen3 reasons before it answers unless this is False. Thinking stays off.
    think: bool = False


@dataclass(frozen=True)
class AgentConfig:
    max_steps: int = 8
    max_tool_retries: int = 1
    traces_dir: str = "host/traces"
    logs_dir: str = "logging"


@dataclass(frozen=True)
class PolicyConfig:
    probation_days: int = 90


@dataclass(frozen=True)
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)

    def __post_init__(self) -> None:
        if self.agent.max_steps < 1:
            raise ValueError("agent.max_steps must be >= 1")
        if self.agent.max_tool_retries < 0:
            raise ValueError("agent.max_tool_retries must be >= 0")
        if self.llm.timeout_seconds <= 0:
            raise ValueError("llm.timeout_seconds must be > 0")
        if self.policy.probation_days < 0:
            raise ValueError("policy.probation_days must be >= 0")


def _coerce(raw: str, current: Any) -> Any:
    if isinstance(current, bool):
        return raw.strip().lower() in {"1", "true", "yes"}
    if isinstance(current, int):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    if isinstance(current, tuple):
        return tuple(raw.split())
    return raw


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build a Config from defaults plus MCPLAB_* environment overrides."""
    env = os.environ if env is None else env
    cfg = Config()
    for section in fields(cfg):
        section_obj = getattr(cfg, section.name)
        updates = {}
        for f in fields(section_obj):
            key = f"{ENV_PREFIX}{section.name}_{f.name}".upper()
            if key in env:
                try:
                    updates[f.name] = _coerce(env[key], getattr(section_obj, f.name))
                except ValueError as exc:
                    raise ValueError(f"Invalid value for {key}: {env[key]!r}") from exc
        if updates:
            cfg = replace(cfg, **{section.name: replace(section_obj, **updates)})
    return cfg


config = load_config()
