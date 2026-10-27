---
description: "Test conventions for the heat_planner agent: pytest, mocking BigQuery and ADK, fixtures."
paths:
  - "agent/tests/**"
---

# Testing Instructions

> Scope: `agent/tests/**` — how this repo tests `agent/heat_planner/`.

## Evidence Used

| Evidence | What it showed |
|---|---|
| `agent/tests/conftest.py` | Autouse fixture sets `GOOGLE_CLOUD_PROJECT=test-project` and clears `prediction._coverage`'s `lru_cache` before/after every test |
| `agent/tests/test_tools.py` | BigQuery is replaced with a `fake_runner(*responses)` closure via `monkeypatch.setattr(module, "run_query", ...)` — real BigQuery is never called |
| `agent/tests/test_service.py` | The real ADK `Runner`/`Agent`/sub-agent/callback loop is driven end to end with a `ScriptedLlm` that yields pre-scripted `function_call`/text parts — no live Gemini call, but no mocking of ADK's own routing either |
| `agent/tests/test_api.py` | FastAPI `TestClient` against the real `app`; `service.run` is monkeypatched per test, not the HTTP layer |
| `agent/requirements-dev.txt` | `pytest>=8`, `httpx>=0.27` (FastAPI's `TestClient` needs httpx) |

## Rules

- ✅ Mock at the `run_query` boundary (`bq.py`), never inside a tool function — this keeps the tool's own logic (validation, coverage check, shaping) under test.
- ✅ Use `fake_runner(*responses)` (defined per test file as needed, see `test_tools.py`) to return a *queue* of responses for multi-query tools (e.g. `prediction.predict_heat_offset` issues a coverage query, then the `ML.EXPLAIN_PREDICT` query).
- ✅ To test the agent tree without a live Gemini call, use a `ScriptedLlm` (pattern in `test_service.py`) rather than mocking `service.run` itself when the test needs to verify routing or callback behavior.
- ✅ New tools must get both: a direct unit test (validation, success, error) in `test_tools.py`-style, and at least indirect coverage through `test_service.py`'s scripted-agent loop if they're wired into a sub-agent.
- ❌ Never call live BigQuery or Vertex AI from a test. If a new integration needs testing, add a seam like `bq.run_query` that can be monkeypatched — don't reach for `unittest.mock.patch` on the SDK client directly.
- ❌ Don't assert on exact floating-point equality from BQML-style computations — round first (see `prediction.py`'s `round(..., 2)` pattern) and test the rounded value, as existing tests do.

## Anti-patterns

- ❌ Testing `agent/heat_planner/config.py` behavior indirectly only — there is currently no direct unit test for `load_settings()`; if you touch `config.py`, add one rather than relying on downstream tests to catch a regression (see `docs/governance/bootstrap-runs/2026-10-27/facts/instruction-topology.yml`'s `not_covered_by_tests`).

## References

- `CLAUDE.md` — hub
- `.claude/rules/bigquery.md` — the SQL-safety pattern these tests verify
- `.claude/rules/adk-agent.md` — the agent tree these tests drive

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
