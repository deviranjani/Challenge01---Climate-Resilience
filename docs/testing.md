# Test Strategy

See `.claude/rules/testing.md` for the authoritative, evidence-backed rules and
`.claude/skills/testing/SKILL.md` for the how-to walkthrough. This page is the quick
human-facing summary.

## What to test

- Every tool function: input validation, the success path, and the error path (BigQuery
  returns nothing / an out-of-range input).
- Agent routing and callback behavior, end to end, using a `ScriptedLlm` rather than mocking
  `service.run` directly, whenever routing itself is what changed.
- New API routes: status codes for success, validation failure (422), and the mapped domain
  error (503).

## What NOT to test

- Framework internals (ADK's own `Runner`/`transfer_to_agent` mechanics) — assume they work;
  test that *this repo's* agents and tools are wired into them correctly.
- Exact floating-point output of a BQML-style computation — round first, then assert, as the
  existing tests do (`result["predicted_offset_f"] == 3.14`, not an unrounded float compare).

## Mocking strategy

BigQuery: monkeypatch the module-level `run_query` reference (`fake_runner` pattern, queue of
responses, one per expected query). Gemini/ADK: a `ScriptedLlm` subclass of `BaseLlm` that
yields pre-scripted function-call/text parts, driving the real `Runner` end to end. Neither
BigQuery nor Vertex AI is ever called live in the test suite.

## Coverage target

No formal coverage threshold is enforced in CI as of this bootstrap run (2026-10-27) — see
`docs/governance/bootstrap-runs/2026-10-27/facts/instruction-topology.yml`'s
`not_covered_by_tests` for the two known gaps (`config.py:load_settings()` has no direct
test; the step-budget truncation path in `callbacks.py` is only reached indirectly).

## Running the suite

```bash
cd agent
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

or `make test-agent` from the repo root.
