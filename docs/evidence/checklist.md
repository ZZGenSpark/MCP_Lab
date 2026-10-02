# PDF evidence checklist

Capture these in order.

1. `docs/requirements.md` — request fields, the policy table, and the approve / deny / escalate rules.
2. Minimal client and server output in `docs/evidence/minimal_connection.txt` (from `poc/`).
3. `server/src/equipment_server/server.py` and `tools.py` with the four tools.
4. `server/tests/` and a passing `pytest` run.
5. Host loop in `host/src/equipment_host/react.py` and the MCP connection in `client/src/equipment_client/session.py`.
6. ReAct traces in `host/traces/` for the six demo requests (an approve, three denials, two escalations).
7. Final decisions in `host/traces/decisions.txt`, including denial and escalation reason codes.
8. Reflection confirm and revise lines in the traces (scenario 1 confirmed, scenario 5 revised after an injected "will ship tomorrow" draft).
9. A green GitHub Actions run of `.github/workflows/ci.yml`.
