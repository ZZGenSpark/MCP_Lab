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

That calls Ollama at `http://localhost:11434` with `qwen3:8b` and writes traces to `host/traces/`. Thinking is off (`MCPLAB_LLM_THINK=false`), so the model answers without a reasoning pass. The model calls tools through Ollama `tool_calls`. Start Ollama first (`ollama serve`).

`run_demo` keeps one server process for all nine scenarios. Review tickets are saved in `logging/flags.json`, so a later request sees a ticket opened by an earlier one, including a second `run_one`. The duplicate-flag check uses that file. `run_demo` clears it at the start so the nine scenarios begin at `REV-0001`. To empty that file without running the demo:

```bash
python -m equipment_host.clear_flags
```

One question, passed as arguments. State a reason: a request with no reason of at least 10 characters is escalated as `VAGUE_REQUEST`.

```bash
python -m equipment_host.run_one Employee E1001 asks for a monitor. Reason: I need a monitor for my desk. Today is 2026-01-01.
```

Each run also writes a flow log under `logging/`. Read it top to bottom. Every step names the function, the previous component's output, the validations that ran, and this step's output. The path is printed as `flow log:`.

Docker:

```bash
docker compose build
docker compose up -d
docker exec -it mcp-lab bash
```

`docker-compose.yml` points the container at the Ollama on your machine (`MCPLAB_LLM_BASE_URL=http://host.docker.internal:11434`), so start Ollama on the host and run `python -m equipment_host.run_demo` from `/workspace` inside the container.

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
| `MCPLAB_LLM_MODEL` | `qwen3:8b` |
| `MCPLAB_LLM_FALLBACK_MODEL` | `mistral` |
| `MCPLAB_LLM_TEMPERATURE` | `0` |
| `MCPLAB_LLM_TIMEOUT_SECONDS` | `120` |
| `MCPLAB_LLM_THINK` | `false` |
| `MCPLAB_AGENT_MAX_STEPS` | `8` |
| `MCPLAB_AGENT_MAX_TOOL_RETRIES` | `1` |
| `MCPLAB_AGENT_TRACES_DIR` | `host/traces` |
| `MCPLAB_AGENT_LOGS_DIR` | `logging` |
| `MCPLAB_POLICY_PROBATION_DAYS` | `90` |

Tuple fields such as `MCPLAB_SERVER_ARGS` are split on spaces. `.env` is ignored; the committed file is `config.py`.

## Layout

| Path | Role |
| --- | --- |
| `server/` | MCP server. Tools, validation, mock data. |
| `client/` | MCP stdio client. No equipment policy. |
| `host/` | Ollama, ReAct, guardrails, reflection. |
| `logging/` | One flow log per run. Host, client, and server append to it. |
| `tests_e2e/` | Host, client, and the real server. The model is scripted. |
| `poc/` | Minimal one-tool connection proof. |
| `docs/evidence/` | PDF checklist and the captured minimal connection. |
