# MCP_Lab

IT equipment requests split into an MCP server, an MCP client, and a host that runs a ReAct loop against local Ollama. Policy rules are in [docs/requirements.md](docs/requirements.md). The component diagram is in [docs/architecture.md](docs/architecture.md).

![CI](https://github.com/ZZGenSpark/MCP_Lab/actions/workflows/ci.yml/badge.svg)

## Run

```bash
pip install -e ".[dev]"
python -m equipment_server
```

The host starts the server itself over stdio:

```bash
python -m equipment_host.run_demo
```

That calls Ollama at `http://localhost:11434` with `llama3.2:3b` and writes traces to `host/traces/`. Start Ollama first (`ollama serve`).

Docker:

```bash
docker compose build
docker compose up -d
docker exec -it mcp-lab bash
```

Inside the container, `ollama serve` in one shell, then `python -m equipment_host.run_demo` from `/workspace`.

## Tests

```bash
ruff check .
ruff format --check .
pytest -q -m "not live" --cov
pytest -q tests_e2e -m "not live"
```

`pytest -m live` runs two scenarios against a local Ollama model. CI does not run that marker.

## Configuration

Defaults live in `config.py`. Override any field with `MCPLAB_<SECTION>_<FIELD>`:

| Variable | Default |
| --- | --- |
| `MCPLAB_SERVER_COMMAND` | the current Python |
| `MCPLAB_SERVER_ARGS` | `-m equipment_server` |
| `MCPLAB_LLM_BASE_URL` | `http://localhost:11434` |
| `MCPLAB_LLM_MODEL` | `llama3.2:3b` |
| `MCPLAB_LLM_FALLBACK_MODEL` | `mistral` |
| `MCPLAB_LLM_TEMPERATURE` | `0` |
| `MCPLAB_LLM_TIMEOUT_SECONDS` | `60` |
| `MCPLAB_AGENT_MAX_STEPS` | `8` |
| `MCPLAB_AGENT_MAX_TOOL_RETRIES` | `1` |
| `MCPLAB_AGENT_TRACES_DIR` | `host/traces` |
| `MCPLAB_POLICY_PROBATION_DAYS` | `90` |

Tuple fields such as `MCPLAB_SERVER_ARGS` are split on spaces. `.env` is ignored; the committed file is `config.py`.

## Layout

| Path | Role |
| --- | --- |
| `server/` | MCP server. Tools, validation, mock data. |
| `client/` | MCP stdio client. No equipment policy. |
| `host/` | Ollama, ReAct, guardrails, reflection. |
| `tests_e2e/` | Host, client, and the real server. The model is scripted. |
| `poc/` | Minimal one-tool connection proof. |
| `docs/evidence/` | PDF checklist and the captured minimal connection. |
