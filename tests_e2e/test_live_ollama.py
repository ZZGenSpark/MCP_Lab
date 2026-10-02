"""Optional live check. Run with ``pytest -m live`` when Ollama is up."""

from __future__ import annotations

import asyncio
import urllib.request

import pytest
from equipment_host.llm import OllamaLLM
from equipment_host.react import handle_request

import config as root_config


@pytest.mark.live
def test_live_approve_and_role_deny() -> None:
    cfg = root_config.load_config()
    try:
        with urllib.request.urlopen(
            f"{cfg.llm.base_url}/api/version", timeout=3
        ) as response:
            response.read()
    except OSError:
        pytest.skip("Ollama is not running")
    llm = OllamaLLM(
        cfg.llm.base_url,
        cfg.llm.model,
        temperature=cfg.llm.temperature,
        timeout=cfg.llm.timeout_seconds,
        fallback_model=cfg.llm.fallback_model,
    )
    approve = asyncio.run(
        handle_request(
            "Employee E1001 is standard and needs a first monitor. None is on file.",
            llm,
        )
    )
    deny = asyncio.run(
        handle_request(
            "Contractor E1002 is asking for a laptop.",
            llm,
        )
    )
    assert approve.decision == "approve"
    assert deny.decision == "deny"
    assert deny.reason_code == "ROLE_NOT_ELIGIBLE"
