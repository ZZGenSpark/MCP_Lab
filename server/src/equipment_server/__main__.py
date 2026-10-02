"""Entrypoint for ``python -m equipment_server``."""

from __future__ import annotations

from equipment_server.server import run


def main() -> None:
    """Run the equipment MCP server over stdio."""
    run()


if __name__ == "__main__":
    main()
