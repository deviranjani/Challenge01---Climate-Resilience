---
name: database
description: 'Reference for this repo''s BigQuery dataset — table schemas, the offset_model, and how to query them safely. Use when: writing a new query against a4i_climate, checking a table/column name, or debugging an empty-result tool. Trigger phrases: "what tables exist", "what columns does this table have", "query the dataset", "debug this empty result".'
---

# Database (BigQuery)

## When to Use This Skill

When writing a new query against the `a4i_climate` BigQuery dataset, checking a table or
column name before using it in a tool, or debugging why a tool returned no rows.

## Prerequisites

Read `.claude/rules/bigquery.md` for the safety rules this skill assumes.

## Dataset

`a4i_climate` (configurable via `BQ_DATASET`, default set in `config.py`), region `US`
(configurable via `BQ_LOCATION`).

## Tables

| Table | What it is | Key columns referenced in code |
|---|---|---|
| `heat_observations` | Street-level NOAA Heat Watch readings, one campaign day | `latitude`, `longitude`, `temp_f` (`bq.py` via `tools/prediction.py:_coverage`, `mapdata.py:measured_points`) |
| `station_daily_temps` | 7 years of daily station maximums | `observation_date`, `max_temp_f` (`tools/history.py`) |
| `tract_demographics` | Census-tract demographics | `geo_id`, `tract_lat`, `tract_lon`, `median_age`, `poverty_rate`, `no_vehicle_rate`, `total_pop`, `median_year_structure_built` (`tools/prediction.py`, `tools/community.py`) |

Census "not available" sentinel: `-666666666`. `tools/prediction.py:29` (`TRACT_CLEAN_SQL`)
converts out-of-range `median_age`/`median_year_structure_built` to `NULL` rather than
passing the sentinel into the model.

## Model

`offset_model` (configurable via `BQML_MODEL`) — a BigQuery ML model predicting the
**offset**: degrees Fahrenheit a location runs hotter (+) or cooler (-) than its city's
campaign-day average. Always call it via `ML.EXPLAIN_PREDICT`, never `ML.PREDICT` — see
`.claude/rules/bigquery.md` and `docs/adr/ADR-001-bigquery-ml-explain-predict-for-heat-offset.md`.

Feature columns (`tools/prediction.py:35`, `FEATURE_SQL`): `latitude`, `longitude`,
`dist_center_km`, `lat_sq`, `lon_sq`, `lat_lon`, plus the cleaned demographic columns above.
**These must exactly match the training table** — if the data/training side changes
features, `FEATURE_SQL` changes here and nowhere else.

## Debugging an Empty Result

1. Confirm the dataset is loaded: `bash scripts/load.sh --list` then `bash scripts/load.sh <city>` if needed (see `scripts/README.md`).
2. Check `_within_coverage()` isn't silently refusing the location — a location outside the `heat_observations` bounding box returns `status: "out_of_coverage"`, not an error.
3. Check `_coverage()`'s `lru_cache` isn't stale after a reload — in tests, `conftest.py`'s autouse fixture clears it; in a long-running process, nothing currently invalidates it after the first call (a known limitation, not a bug to silently "fix" without discussion — see `docs/governance/bootstrap-runs/2026-10-27/facts/concerns.md`).

## Loading / Reloading Data

```bash
bash scripts/load.sh dallas       # or any city from --list
bash scripts/load.sh --list
```

Safe to re-run — every table is fully replaced, never appended to (`scripts/load.sh` header comment).

## Checklist

- [ ] New query uses an existing table/column name from the table above, verified, not guessed
- [ ] A new model-serving query uses `ML.EXPLAIN_PREDICT`
- [ ] Any new feature added to `FEATURE_SQL` is coordinated with the data/training side first

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
