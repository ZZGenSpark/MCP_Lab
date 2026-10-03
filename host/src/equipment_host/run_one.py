"""Run one equipment request passed on the command line."""

from __future__ import annotations

import argparse
import asyncio

import config as root_config
import flowlog
from equipment_host.llm import OllamaLLM
from equipment_host.react import handle_request


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the question from the remaining command-line words."""
    parser = argparse.ArgumentParser(
        prog="python -m equipment_host.run_one",
        description="Run one IT equipment request through the host.",
    )
    parser.add_argument(
        "question",
        nargs="+",
        help="Request text. Separate words are joined with spaces.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Call local Ollama for one question and print the trace."""
    question = " ".join(parse_args(argv).question)
    cfg = root_config.load_config()
    log_path = flowlog.begin(cfg.agent.logs_dir, question, question)
    llm = OllamaLLM.from_config(cfg.llm)
    result = asyncio.run(
        handle_request(
            question,
            llm,
            max_steps=cfg.agent.max_steps,
            max_tool_retries=cfg.agent.max_tool_retries,
        )
    )
    reflection = result.reflection or {}
    print(f"flow log: {log_path}")
    print(result.trace)
    print(
        f"decision={result.decision} "
        f"reason={result.reason_code or '-'} ticket={result.ticket_id or '-'} "
        f"reflection={reflection.get('verdict', '-')}"
    )
    print(result.text)


if __name__ == "__main__":
    main()
