# equipment_client

MCP client library. It connects to the equipment server over stdio, lists tools, and calls them.

## Run

Library only. The host imports `equipment_client` and opens a session. Install from the repo root:

```bash
pip install -e ".[dev]"
```

## Imports

This package imports the `mcp` SDK. The server launch command comes from the root `config` module. It does not import `equipment_server`, `equipment_host`, or equipment policy rules.
