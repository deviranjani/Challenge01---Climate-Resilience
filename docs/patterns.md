# Coding Patterns

Repo-specific patterns for `agent/heat_planner/`. See `CLAUDE.md`'s Instruction Map and the
matching `.claude/rules/*.md` file for the authoritative, evidence-backed version of each
pattern below — this page is a human-readable summary, not a second source of truth.

## Error handling

- Every tool function is wrapped in `tools/_common.py`'s `@safe_tool` — exceptions never
  reach the LLM; they become `{"status": "error", "message": ...}`.
- `ToolError` (raised for expected failures: bad input, no data, BigQuery refused) is the
  only exception type tool code should raise deliberately; anything else is caught generically
  by `safe_tool` and reported without leaking internal detail.
- FastAPI maps domain errors to HTTP status explicitly: `AgentError`/`ToolError` → 503,
  everything else → a global handler returning only the exception's type name (`api.py:33`).

## Retry

No retry logic exists today — BigQuery and Vertex AI calls fail fast and surface as a
structured error. A rate-limited Gemini call (`"ResourceExhausted"`/`"429"`) is caught and
turned into a plain "busy, try again" message (`service.py:97`) rather than retried
automatically.

## Naming conventions

- Tool functions: a verb + noun describing what the agent gets back (`predict_heat_offset`,
  `rank_response_sites`, `heat_frequency`, `community_profile`).
- Private/internal helpers: leading underscore (`_within_coverage`, `_attributions`, `_cached`).
- Sub-agents: `<domain>_analyst` (`prediction_analyst`, `history_analyst`, `community_analyst`).

## Caching

`mapdata.py`'s `_cached()` is a 600-second, thread-lock-guarded, in-process dict cache — used
only for the map/graph read endpoints, not the chat tools. It does not share state across
multiple Cloud Run instances (see `docs/governance/bootstrap-runs/2026-10-27/facts/concerns.md`, C5).

## Configuration

All runtime configuration is read from the environment through `config.py:load_settings()`,
returning a frozen `Settings` dataclass. No module reads `os.environ` directly except
`config.py` and `mapdata.py:maps_config()` (the Maps key, which is client-facing config, not
a server secret).

## What NOT to do

- Don't build SQL by string-interpolating a user/model-supplied value — see `.claude/rules/bigquery.md`.
- Don't let a new tool skip `@safe_tool`.
- Don't add a second BigQuery client factory — reuse `bq._client()`.
- Don't assume a correlation ID, metric, or trace exists — see `.claude/rules/observability.md`.
