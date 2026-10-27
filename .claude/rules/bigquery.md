---
description: "BigQuery client, query-safety, and BQML / ML.EXPLAIN_PREDICT patterns."
paths:
  - "agent/heat_planner/bq.py"
  - "agent/heat_planner/tools/**"
---

# BigQuery Instructions

> Scope: the BigQuery access layer (`bq.py`) and every tool that queries it (`tools/`).

## Evidence Used

| Evidence | What it showed |
|---|---|
| `bq.py:33` | `run_query()` is the single entry point; every caller passes fixed SQL text + `bigquery.ScalarQueryParameter` values — never string-interpolated user input |
| `bq.py:41,43` | `maximum_bytes_billed=settings.max_bytes_billed` (default 1 GB) and `max_rows` enforced on every query |
| `bq.py:22` | `_client()` is `functools.lru_cache(maxsize=1)` — one client per process |
| `tools/prediction.py:110` | `ML.EXPLAIN_PREDICT` (not `ML.PREDICT`) used so the agent can report per-feature attributions, not just a number |
| `tools/prediction.py:35` | `FEATURE_SQL` must exactly match the training table's feature columns — "if the data lane changes features, change them there only" |
| `tools/prediction.py:60` | `_within_coverage()` refuses predictions outside the bounding box of `heat_observations` before calling the model — avoids extrapolation |
| `tools/_common.py:18` | `safe_tool` decorator: every tool function is wrapped so a `ToolError` becomes `{"status": "error", ...}` and any other exception becomes a generic message that never leaks internal detail |

## Rules

- ✅ Every new query goes through `bq.run_query()` with a parameterized `bigquery.ScalarQueryParameter` for every user-influenced value — never f-string a user-supplied latitude/longitude/threshold directly into SQL. Values that come from a tool's own fixed logic (table names, LIMIT counts) may be f-strung, as the existing code does.
- ✅ Wrap every tool function in `tools/_common.py`'s `@safe_tool` decorator so `ToolError` and unexpected exceptions both become a structured `{"status": "error", "message": ...}` dict instead of an unhandled exception (verified by `test_tools.py::test_safe_tool_turns_exceptions_into_errors`: internal exception text never reaches the message).
- ✅ Validate all tool numeric input with `validate_coordinates()` / `clamp_int()` from `tools/_common.py` before building SQL.
- ✅ Use `ML.EXPLAIN_PREDICT`, not `ML.PREDICT`, for any new model-serving tool — the attributions are the whole point of this challenge's required differentiator (BigQuery ML, per root `README.md`).
- ✅ Check `_within_coverage()` (or an equivalent bounding-box guard) before calling a prediction model for a new location-based tool — predictions outside the measured area extrapolate wildly (`tools/prediction.py:200` comment: "tens of degrees").
- ❌ Never add a second BigQuery client factory — reuse `bq._client()`.
- ❌ Never drop `maximum_bytes_billed`/`max_rows` on a new query — this is the only cost ceiling in the codebase.

## Anti-patterns

- ❌ Letting the LLM construct SQL text. Tools pass fixed SQL + parameters; the model only ever supplies tool *arguments* (latitude, longitude, threshold_f, top_n), never SQL.

## References

- `CLAUDE.md` — hub
- `.claude/rules/security.md` — why parameterized queries matter here (SQL-injection-by-LLM prevention)
- `.claude/rules/integrations.md` — BigQuery dataset/table/model names and env vars
- `docs/adr/ADR-001-bigquery-ml-explain-predict-for-heat-offset.md`

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
