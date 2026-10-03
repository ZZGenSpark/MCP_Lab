"""Wipe saved review tickets without running the demo."""

from __future__ import annotations

from equipment_host.connection import clear_saved_flags, flag_file


def main() -> None:
    """Replace logging/flags.json with an empty ticket list."""
    clear_saved_flags()
    print(f"cleared: {flag_file()}")


if __name__ == "__main__":
    main()
