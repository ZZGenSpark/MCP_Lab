# equipment_host

Host application. It owns the Ollama model, the ReAct loop, guardrails, and reflection.

## Run

Library package. Install from the repo root:

```bash
pip install -e ".[dev]"
python -m equipment_host.run_demo
python -m equipment_host.run_one Employee E1001 asks for a monitor. Reason: I need a monitor for my desk. Today is 2026-01-01.
python -m equipment_host.clear_flags
pytest host/tests tests_e2e -m "not live" -q
```

`run_demo` uses `MCPLAB_LLM_MODEL` (default `qwen3:8b`, thinking off through `MCPLAB_LLM_THINK=false`) and writes `host/traces/`. The model selects tools with Ollama `tool_calls`. Pass the requester's reason in the request text: a request with no reason of at least 10 characters is escalated as `VAGUE_REQUEST`. It opens one stdio server and sends all nine scenarios through that session: an approve, three denials, and five escalations (borderline laptop, new hire, data conflict, reported hardware failure, vague request). Each request states a reason in the wording of the scenario table in `docs/requirements.md`. `run_one` sends the argument text as a single request and prints the trace. Both write a flow log under `logging/` (`MCPLAB_AGENT_LOGS_DIR`) and save review tickets to `logging/flags.json`, which the next server process loads. `run_demo` clears that file first. `clear_flags` empties it without running a request. `MCPLAB_AGENT_MAX_STEPS` and `MCPLAB_AGENT_MAX_TOOL_RETRIES` bound the loop.

## Escalations

When `check_request_eligibility` returns `eligible: "unclear"`, the ticket reason is written as `<reason_code>: <rule>` (for example `TENURE_UNDER_90_DAYS: tenure is 89 days, under the 90-day probation`). The host rewrites a reason from the model that does not already start with the code, and the trace shows a `Guardrail: ticket reason set to ...` line. If the model never opens the ticket, the host opens it with the same reason; a request that names no item gets "<employee> sent a request that names no item."

Reflection is a second call to the same model, after the decision is already accepted. The model judges the draft against the tool observations. A `confirmed` verdict keeps the draft. A `revised` verdict replaces it with the model's `final_text`. The trace prints that critique as `Reflection critique`. After the judge, the host drops any date, number, or id in the reply that does not appear in the tool arguments or results, and marks the verdict `revised`. A promise with no such value, such as "will ship tomorrow", is left for the model. A decision that contradicts `eligible` is also marked `revised`, and the decision itself stays what the guardrails accepted.

## Imports

This package imports `equipment_client` and the root `config` module. It discovers tools at runtime with `list_tools`. It does not import `equipment_server`.
