# Phase 1 facts — observability

## What exists
- Standard library `logging`, configured once in `agent/heat_planner/agent.py:13` (`logging.basicConfig(level=INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")`).
- Module-level loggers in `api.py`, `bq.py`, `mapdata.py`, `callbacks.py`, `service.py` (`logging.getLogger(__name__)` or a named logger).
- `bq.py:50` logs query failures with `logger.exception` (full traceback) before raising `ToolError`; `bq.py:52` logs row counts on success.
- `api.py:33` global FastAPI exception handler logs `logger.exception("request failed")` for any unhandled error, returning only `{"error": type(exc).__name__}` to the client (no internal detail leaked over HTTP).
- `callbacks.py` builds an in-memory, per-request **tool call trace** (`ctx.steps`): tool name, args, start time, elapsed ms, and error message if the tool returned `status: "error"`. This trace is returned to the UI as `steps` in the `/api/chat` response (`service.py:101`) and rendered as cards — it is a request-scoped debugging aid, not an exported observability signal.

## What does not exist (gap, not fabricated)
- No structured/JSON logging — plain `%`-formatted log lines only.
- No correlation ID / request ID propagated into BigQuery query labels or Gemini calls.
- No metrics (counters, latency histograms) exported anywhere.
- No distributed tracing / span export (no OpenTelemetry, no Cloud Trace integration found).
- No external log sink configured beyond default Cloud Run stdout/stderr capture (Dockerfile runs `uvicorn ... --no-access-log`, further reducing what reaches Cloud Logging).

This gap is recorded in `CLAUDE.md`'s `## Concerns` section rather than invented as a rule to follow — there is no established repo pattern for structured observability to document.
