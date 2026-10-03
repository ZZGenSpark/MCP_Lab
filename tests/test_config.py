"""Defaults, MCPLAB_* overrides, and rejected config values."""

from __future__ import annotations

import pytest

from config import (
    AgentConfig,
    Config,
    LLMConfig,
    PolicyConfig,
    ServerConfig,
    load_config,
)


def test_defaults() -> None:
    cfg = load_config({})
    assert cfg == Config(
        server=ServerConfig(),
        llm=LLMConfig(),
        agent=AgentConfig(),
        policy=PolicyConfig(),
    )
    assert cfg.server.command
    assert cfg.server.args == ("-m", "equipment_server")
    assert cfg.llm.base_url == "http://localhost:11434"
    assert cfg.llm.model == "qwen3:8b"
    assert cfg.llm.temperature == 0.0
    assert cfg.llm.timeout_seconds == 120
    assert cfg.llm.think is False
    assert cfg.agent.max_steps == 8
    assert cfg.agent.max_tool_retries == 1
    assert cfg.agent.traces_dir == "host/traces"
    assert cfg.agent.logs_dir == "logging"
    assert cfg.policy.probation_days == 90


def test_env_overrides_each_type() -> None:
    cfg = load_config(
        {
            "MCPLAB_LLM_MODEL": "mistral",
            "MCPLAB_AGENT_MAX_STEPS": "4",
            "MCPLAB_LLM_TEMPERATURE": "0.2",
            "MCPLAB_SERVER_ARGS": "-m equipment_server --stdio",
        }
    )
    assert cfg.llm.model == "mistral"
    assert cfg.llm.base_url == "http://localhost:11434"
    assert cfg.agent.max_steps == 4
    assert cfg.agent.traces_dir == "host/traces"
    assert cfg.llm.temperature == 0.2
    assert cfg.server.args == ("-m", "equipment_server", "--stdio")
    assert cfg.server.command


def test_think_can_be_switched_on_from_the_environment() -> None:
    assert load_config({"MCPLAB_LLM_THINK": "true"}).llm.think is True
    assert load_config({"MCPLAB_LLM_THINK": "false"}).llm.think is False


def test_invalid_override_is_rejected() -> None:
    with pytest.raises(ValueError, match="MCPLAB_AGENT_MAX_STEPS"):
        load_config({"MCPLAB_AGENT_MAX_STEPS": "many"})
    with pytest.raises(ValueError, match="MCPLAB_LLM_TEMPERATURE"):
        load_config({"MCPLAB_LLM_TEMPERATURE": "warm"})
    with pytest.raises(ValueError, match="agent.max_steps"):
        load_config({"MCPLAB_AGENT_MAX_STEPS": "0"})
    with pytest.raises(ValueError, match="llm.timeout_seconds"):
        load_config({"MCPLAB_LLM_TIMEOUT_SECONDS": "0"})
    with pytest.raises(ValueError, match="policy.probation_days"):
        load_config({"MCPLAB_POLICY_PROBATION_DAYS": "-1"})
