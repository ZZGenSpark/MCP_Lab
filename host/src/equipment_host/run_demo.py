"""Run the nine demo requests and write traces plus final decisions.

Each request states a reason, worded like the scenario table in
docs/requirements.md. The eligibility check judges that reason.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import config as root_config
import flowlog
from equipment_host.connection import (
    clear_saved_flags,
    open_equipment_session,
    use_flow_pointer,
)
from equipment_host.llm import OllamaLLM
from equipment_host.react import handle_request

SCENARIOS = (
    {
        "name": "01_approve_monitor",
        "request": (
            "Employee E1001 asks for a monitor. "
            "Reason: I need a monitor for my desk. Today is 2026-01-01."
        ),
        "overcommit": False,
    },
    {
        "name": "02_deny_contractor_laptop",
        "request": (
            "Contractor E1002 asks for a laptop. "
            "Reason: I need a laptop for client work. Today is 2026-01-01."
        ),
        "overcommit": False,
    },
    {
        "name": "03_deny_unknown_employee",
        "request": (
            "Employee E9999 asks for a monitor. "
            "Reason: Please issue a monitor. Today is 2026-01-01."
        ),
        "overcommit": False,
    },
    {
        "name": "04_deny_unknown_item",
        "request": (
            "Employee E1001 asks for a standing desk. "
            "Reason: I need a standing desk. Today is 2026-01-01."
        ),
        "overcommit": False,
    },
    {
        "name": "05_escalate_borderline_laptop",
        "request": (
            "Employee E1003 asks for a laptop. "
            "Reason: My laptop is 4 years old and slow. Today is 2026-01-01."
        ),
        "overcommit": True,
    },
    {
        "name": "06_escalate_new_hire",
        "request": (
            "New hire E1004 is under 90 days and asks for a monitor. "
            "Reason: I need a monitor for my desk. Today is 2026-01-01."
        ),
        "overcommit": False,
    },
    {
        "name": "07_escalate_data_conflict",
        "request": (
            "Contractor E1005 asks for a laptop. "
            "Reason: My laptop no longer works. Today is 2026-01-01."
        ),
        "overcommit": False,
    },
    {
        "name": "08_escalate_hardware_failure",
        "request": (
            "Employee E1006 asks for a monitor. "
            "Reason: My monitor is broken. Today is 2026-01-01."
        ),
        "overcommit": False,
    },
    {
        "name": "09_escalate_vague_request",
        "request": (
            "Employee E1001 asks for equipment but does not say which item. "
            "Reason: Help. Today is 2026-01-01."
        ),
        "overcommit": False,
    },
)


def main() -> None:
    """Call local Ollama for each scenario on one server and save the traces."""
    asyncio.run(run_scenarios())


async def run_scenarios() -> None:
    """Run every scenario on one stdio server so later requests see open tickets."""
    cfg = root_config.load_config()
    llm = OllamaLLM.from_config(cfg.llm)
    out = Path(cfg.agent.traces_dir)
    out.mkdir(parents=True, exist_ok=True)
    previous_pointer = os.environ.get(flowlog.ENV_POINTER)
    use_flow_pointer()
    clear_saved_flags()
    lines = ["# Demo decisions", ""]
    try:
        async with open_equipment_session() as session:
            for scenario in SCENARIOS:
                log_path = flowlog.begin(
                    cfg.agent.logs_dir,
                    str(scenario["name"]),
                    str(scenario["request"]),
                )
                result = await handle_request(
                    str(scenario["request"]),
                    llm,
                    session=session,
                    max_steps=cfg.agent.max_steps,
                    max_tool_retries=cfg.agent.max_tool_retries,
                    inject_overcommit=bool(scenario["overcommit"]),
                )
                (out / f"{scenario['name']}.txt").write_text(
                    result.trace + "\n", encoding="utf-8"
                )
                print(f"flow log: {log_path}")
                reflection = result.reflection or {}
                lines.append(
                    f"{scenario['name']}: decision={result.decision} "
                    f"reason={result.reason_code or '-'} ticket={result.ticket_id or '-'} "
                    f"reflection={reflection.get('verdict', '-')}"
                )
                lines.append(result.text)
                lines.append("")
    finally:
        if previous_pointer is None:
            os.environ.pop(flowlog.ENV_POINTER, None)
        else:
            os.environ[flowlog.ENV_POINTER] = previous_pointer
    (out / "decisions.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
