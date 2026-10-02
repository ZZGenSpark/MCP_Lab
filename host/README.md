# equipment_host

Host application. It owns the Ollama model, the ReAct loop, guardrails, and reflection.

## Run

Library package. Install from the repo root:

```bash
pip install -e ".[dev]"
python -m equipment_host.run_demo
pytest host/tests tests_e2e -m "not live" -q
```

`run_demo` uses `MCPLAB_LLM_MODEL` (default `llama3.2:3b`) and writes `host/traces/`. `MCPLAB_AGENT_MAX_STEPS` and `MCPLAB_AGENT_MAX_TOOL_RETRIES` bound the loop.

## Imports

This package imports `equipment_client` and the root `config` module. It discovers tools at runtime with `list_tools`. It does not import `equipment_server`.
