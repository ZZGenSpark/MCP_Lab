# PDF evidence checklist

Capture these in order.

1. `docs/requirements.md` — request fields, the policy table, and the approve / deny / escalate rules.
2. Minimal client and server output in `docs/evidence/minimal_connection.txt` (from `poc/`).
3. `server/src/equipment_server/server.py` and `tools.py` with the four tools.
4. `server/tests/` and a passing `pytest` run.
5. Host loop in `host/src/equipment_host/react.py` and the MCP connection in `client/src/equipment_client/session.py`.
6. ReAct traces in `host/traces/` for the nine demo requests (an approve, three denials, five escalations). Capture at least these four: `01_approve_monitor`, `02_deny_contractor_laptop`, `05_escalate_borderline_laptop`, and `08_escalate_hardware_failure`.
7. Final decisions in `host/traces/decisions.txt`, including denial and escalation reason codes. Each escalation names its ticket id and reason code.
8. Reflection lines in the traces. Scenario 1 is `confirmed`. Scenario 5 injects "will ship tomorrow"; the reflection model is the judge and should return `revised` with that promise removed. Dates, numbers, and ids that are not in the tool observations are removed in code even if the judge confirms them.
9. A green GitHub Actions run of `.github/workflows/ci.yml`.
