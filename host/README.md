# equipment_host

Host application. It owns the Ollama model, the ReAct loop, guardrails, and reflection.

## Run

Library package. Install from the repo root:

```bash
pip install -e ".[dev]"
```

Demo traces are stored in `host/traces/`.

## Imports

This package imports `equipment_client` and the root `config` module. It discovers tools at runtime with `list_tools`. It does not import `equipment_server`.
