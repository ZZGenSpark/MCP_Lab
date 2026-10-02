"""Smoke test: the three packages import and the server entrypoint runs."""

from __future__ import annotations

import equipment_client
import equipment_host
import equipment_server
from equipment_server.__main__ import main


def test_layout_smoke() -> None:
    assert equipment_server.__version__ == "0.1.0"
    assert equipment_client.__version__ == "0.1.0"
    assert equipment_host.__version__ == "0.1.0"
    assert callable(main)
