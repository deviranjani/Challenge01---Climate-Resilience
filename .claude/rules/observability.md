---
description: "What logging/tracing exists today, and what does not — read before assuming observability tooling is in place."
paths:
  - "agent/heat_planner/**"
---

# Observability Instructions

> Scope: logging and the per-request tool trace across `agent/heat_planner/`.

## Evidence Used

| Evidence | What it showed |
|---|---|
| `agent.py:13` | `logging.basicConfig(level=INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")` — the only logging configuration in the repo |
| `bq.py:50,52` | `logger.exception` on query failure (full traceback), `logger.info` with row count on success |
| `api.py:33` | Global exception handler logs `logger.exception("request failed")`, returns only `{"error": type(exc).__name__}` to the client |
| `callbacks.py` | Builds a per-request, in-memory tool-call trace (`ctx.steps`): tool name, args, elapsed ms, error if any — returned to the UI as `steps`, not exported anywhere |
| `agent/Dockerfile:12` | `uvicorn ... --no-access-log` — access logs are explicitly suppressed in the container |

## Rules

- ✅ Use the existing `logging.getLogger(__name__)` pattern for any new module — don't introduce a second logging framework.
- ✅ Log full exception detail server-side with `logger.exception`, and return only a generic, non-leaking message/type to the HTTP client (`api.py`'s pattern) or to the LLM (`safe_tool`'s pattern, see `.claude/rules/bigquery.md`).
- ✅ If you add a new tool, let `callbacks.py`'s existing `before_tool`/`after_tool` wiring capture it automatically — don't build a parallel ad hoc trace.

## What does NOT exist (do not assume otherwise)

- No structured/JSON logging.
- No correlation ID / request ID propagated into BigQuery query labels or Gemini calls.
- No metrics (counters, latency histograms) exported anywhere.
- No distributed tracing / span export (no OpenTelemetry, no Cloud Trace integration).
- No external log sink beyond Cloud Run's default stdout/stderr capture, and access logs are
  explicitly disabled.

If a task requires any of the above, treat it as new work — do not assume a tracing or
metrics pattern already exists to extend.

## Anti-patterns

- ❌ Assuming a correlation/request ID is already threaded through BigQuery calls — it is not. If one is added, propagate it from `api.py`'s request handler through to `bq.run_query`'s job config labels.

## References

- `CLAUDE.md` — hub and `## Concerns` section
- `docs/governance/bootstrap-runs/2026-10-27/facts/observability.md` — the Phase 1 evidence this file is built from

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
