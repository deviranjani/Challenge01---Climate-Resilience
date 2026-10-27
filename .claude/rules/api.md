---
description: "FastAPI route conventions, request validation, and error-to-HTTP mapping."
paths:
  - "agent/heat_planner/api.py"
---

# API Instructions

> Scope: `agent/heat_planner/api.py` — the FastAPI app and its routes.

## Evidence Used

| Evidence | What it showed |
|---|---|
| `api.py:28` | `ChatIn` uses Pydantic `Field(min_length=1, max_length=config.MAX_QUESTION_CHARS)` and `Field(default_factory=list, max_length=24)` to cap user input before it reaches the agent |
| `api.py:33` | A single `@app.exception_handler(Exception)` logs the full traceback server-side and returns only `{"error": type(exc).__name__}` to the client |
| `api.py:62` | `service.AgentError` → HTTP 503 |
| `api.py:66-71` | `_data()` helper wraps every blocking data-loader call (`asyncio.to_thread`) and maps `bq.ToolError` → HTTP 503 |
| `api.py:80` | `Query(..., ge=1, le=mapdata.MAX_POINTS)` bounds the `limit` query param |

## Rules

- ✅ Every request body is a Pydantic model with explicit `max_length`/bounds — never accept an unbounded string or list from the client.
- ✅ Blocking calls (BigQuery, the synchronous ADK `service.run`) go through `asyncio.to_thread()` so the event loop is never blocked — follow the `_data()` / `chat()` pattern for any new endpoint that touches BigQuery or the agent.
- ✅ Map domain errors to HTTP status explicitly: `service.AgentError` and `bq.ToolError` → 503 (service temporarily unavailable), validation errors → FastAPI's built-in 422, anything else → the global handler's 500. Don't introduce a new unhandled-exception path.
- ✅ Never return raw exception text or a stack trace to the client — the global handler intentionally returns only the exception's type name.
- ❌ Don't add a new route that calls `mapdata.*` or `service.run` synchronously without `asyncio.to_thread` — it will block the whole event loop for every concurrent user.

## Anti-patterns

- ❌ Duplicating input-length validation in route-handler code instead of the Pydantic model — `ChatIn`/`Turn` are the single place question/history length limits live.

## References

- `CLAUDE.md` — hub
- `.claude/rules/bigquery.md` — `ToolError` origin
- `.claude/rules/adk-agent.md` — `AgentError` origin

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
