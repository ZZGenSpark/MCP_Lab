# equipment_server

MCP server for IT equipment requests. It exposes tools over stdio.

## Run

From the repo root, after `pip install -e ".[dev]"`:

```bash
python -m equipment_server
pytest server/tests -q
```

Settings for the rest of the lab are `MCPLAB_*` variables documented in the root README. This server does not read them.

## Imports

This package stands alone. It does not import `equipment_client`, `equipment_host`, or the root `config` module.
