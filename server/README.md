# equipment_server

MCP server for IT equipment requests. It exposes tools over stdio.

## Run

From the repo root, after `pip install -e ".[dev]"`:

```bash
python -m equipment_server
pytest server/tests -q
```

Settings for the rest of the lab are `MCPLAB_*` variables documented in the root README. This server does not read them. When `EQUIPMENT_FLAG_STORE` is a file path, open review tickets are loaded from that file and saved after each new ticket. Without it, tickets stay in memory for this process only.

## Imports

This package stands alone. It does not import `equipment_client`, `equipment_host`, or the root `config` module.
