# Phase 1 facts — code patterns

## Agent tree construction
- `agent/heat_planner/agent.py:16` `build_root_agent(ctx, model)` builds a fresh `Agent` per request; `root_agent` at module scope only serves `adk web`/`adk run`.
- `agent/heat_planner/sub_agents.py:18` `build_sub_agents` creates one `Agent` per specialist, each with a **small, disjoint tool set** so ADK's routing stays unambiguous (prediction_analyst: 2 tools, history_analyst: 1, community_analyst: 1).
- `agent/heat_planner/callbacks.py:73` `wire(ctx)` returns the same 4 callbacks (`before_model`, `after_model`, `before_tool`, `after_tool`) for every Agent in the tree, sharing one `AgentContext` (`context.py`) per request.
- `agent/heat_planner/prompts.py` — each agent's instruction is a plain string wrapped in a no-op lambda/provider (`sub_agents.py:13` `_instruction`) specifically so literal `{}` braces in prompt text are never read as ADK session-state template variables.

## Tool safety pattern (`agent/heat_planner/tools/_common.py`)
- `safe_tool` decorator (line 18): every tool function is wrapped so **no exception ever reaches the LLM** — `ToolError` becomes `{"status": "error", "message": ...}`, any other exception becomes a generic `{"status": "error", "message": "Unexpected error in {fn}: {type}"}` that never leaks internal exception text (see `test_tools.py::test_safe_tool_turns_exceptions_into_errors`).
- `validate_coordinates` / `clamp_int` (lines 35, 47): all user-facing numeric tool args are validated and clamped before use; invalid input raises `ToolError`, never a raw exception.
- Coverage gate: `prediction.py:60` `_within_coverage` refuses predictions outside the bounding box of the loaded `heat_observations`, returning `status: "out_of_coverage"` **before** calling the BQML model — avoids extrapolating tens of degrees outside the measured area (`prediction.py:200` comment).

## SQL safety pattern (`agent/heat_planner/bq.py`)
- One function, `run_query()` (line 33), is the only place that calls BigQuery. Every call site passes **fixed SQL text + `bigquery.ScalarQueryParameter` values** — never string-interpolated user input into SQL (verified in `prediction.py`, `community.py`, `history.py`, `mapdata.py`).
- `maximum_bytes_billed` (from `Settings.max_bytes_billed`, default 1 GB) and `max_rows` are enforced on every query — a cost/blast-radius ceiling independent of query content.
- `_client()` is `functools.lru_cache(maxsize=1)` — one BigQuery client per process.

## Error-to-HTTP mapping (`agent/heat_planner/api.py`)
- `service.AgentError` → HTTP 503 (`api.py:62`)
- `bq.ToolError` surfaced through `mapdata` helpers → HTTP 503 via the `_data()` wrapper (`api.py:66`)
- Any other exception → global handler (`api.py:33`) returns `{"error": type(exc).__name__}` with status 500, logged with `logger.exception` server-side (never the raw message to the client)
- Pydantic models (`Turn`, `ChatIn`) enforce `max_length` on every user-supplied string/list before it reaches the agent.

## Caching pattern (`agent/heat_planner/mapdata.py`)
- `_cached()` (line 31) is a small in-process, thread-lock-guarded, 600-second TTL cache keyed by string — used so panning the map UI never re-triggers a BigQuery + BQML call per request. Not shared across processes/instances (no Redis/Memcached) — fine for a single Cloud Run instance, a known limit if scaled horizontally (see `.claude/rules/bigquery.md`).

## Testing pattern
- BigQuery is never called live in tests: `monkeypatch.setattr(module, "run_query", fake_runner(...))` (`test_tools.py:17`).
- The ADK loop is exercised for real (not mocked away) using a `ScriptedLlm` (`test_service.py`) that yields pre-scripted `function_call`/text parts — this drives the actual `Runner` → `Agent` → sub-agent → tool → callback chain with no network call.
- `conftest.py` autouse fixture sets `GOOGLE_CLOUD_PROJECT=test-project` and clears `prediction._coverage`'s `lru_cache` before/after every test (coverage box must be freshly fetched per test).
