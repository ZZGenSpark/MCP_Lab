"""Run the six demo requests and write traces plus final decisions."""

from __future__ import annotations

import asyncio
from pathlib import Path

import config as root_config
from equipment_host.llm import OllamaLLM
from equipment_host.react import handle_request

SCENARIOS = (
    {
        "name": "01_approve_monitor",
        "request": (
            "Employee E1001 is standard and needs a first monitor. "
            "None is on file. Today is 2026-01-01."
        ),
        "overcommit": False,
    },
    {
        "name": "02_deny_contractor_laptop",
        "request": "Contractor E1002 is asking for a laptop. Today is 2026-01-01.",
        "overcommit": False,
    },
    {
        "name": "03_deny_unknown_employee",
        "request": "Employee E9999 asks for a monitor. Today is 2026-01-01.",
        "overcommit": False,
    },
    {
        "name": "04_deny_unknown_item",
        "request": "Employee E1001 asks for a standing desk. Today is 2026-01-01.",
        "overcommit": False,
    },
    {
        "name": "05_escalate_borderline_laptop",
        "request": (
            "Employee E1003 says: my laptop is 4 years old and slow. "
            "Today is 2026-01-01."
        ),
        "overcommit": True,
    },
    {
        "name": "06_escalate_new_hire",
        "request": (
            "New hire E1004 is under 90 days and asks for a monitor. "
            "Today is 2026-01-01."
        ),
        "overcommit": False,
    },
)


def main() -> None:
    """Call local Ollama for each scenario and save the trace."""
    cfg = root_config.load_config()
    llm = OllamaLLM(
        cfg.llm.base_url,
        cfg.llm.model,
        temperature=cfg.llm.temperature,
        timeout=cfg.llm.timeout_seconds,
        fallback_model=cfg.llm.fallback_model,
    )
    out = Path(cfg.agent.traces_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Demo decisions", ""]
    for scenario in SCENARIOS:
        result = asyncio.run(
            handle_request(
                str(scenario["request"]),
                llm,
                max_steps=cfg.agent.max_steps,
                max_tool_retries=cfg.agent.max_tool_retries,
                inject_overcommit=bool(scenario["overcommit"]),
            )
        )
        (out / f"{scenario['name']}.txt").write_text(
            result.trace + "\n", encoding="utf-8"
        )
        reflection = result.reflection or {}
        lines.append(
            f"{scenario['name']}: decision={result.decision} "
            f"reason={result.reason_code or '-'} ticket={result.ticket_id or '-'} "
            f"reflection={reflection.get('verdict', '-')}"
        )
        lines.append(result.text)
        lines.append("")
    (out / "decisions.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
