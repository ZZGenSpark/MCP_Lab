"""server, client, and host may only import what the architecture allows."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RULES = {
    "server/src": ("equipment_client", "equipment_host", "config"),
    "client/src": ("equipment_server", "equipment_host"),
    "host/src": ("equipment_server",),
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_import_boundaries() -> None:
    violations: list[str] = []
    for folder, forbidden in RULES.items():
        for path in (ROOT / folder).rglob("*.py"):
            imported = _imported_modules(path)
            hit = sorted(set(forbidden) & imported)
            if hit:
                violations.append(f"{path.relative_to(ROOT)} imports {hit}")
    assert violations == []
