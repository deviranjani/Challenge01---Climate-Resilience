---
description: "External service inventory: BigQuery, Vertex AI/Gemini, Google Maps JS API, GCS snapshot source."
paths:
  - "agent/heat_planner/config.py"
  - "agent/heat_planner/bq.py"
  - "agent/heat_planner/mapdata.py"
  - "scripts/load.sh"
---

# Integrations Instructions

> Scope: external service configuration and access — what this repo talks to, and how.

## Evidence Used

| Evidence | What it showed |
|---|---|
| `config.py:27` | All external config read from environment via `load_settings()`, no hardcoded project/dataset names |
| `config.py:7-8` | `GOOGLE_GENAI_USE_VERTEXAI` forced `true` — Gemini is always reached through Vertex AI, authenticated by the runtime service account, never a raw API key |
| `mapdata.py:44` | `GOOGLE_MAPS_API_KEY` read directly from `os.environ`, served to the client via `/api/map/config` |
| `scripts/load.sh:21` | `BUCKET="gs://class-demo/a4i-2026/challenge-1-walkability"` — the GCS snapshot source for the headless data-load fallback |
| `agent/README.md` | Google Maps key should be restricted to the Maps JavaScript API and the app's own URLs (no port wildcards) |

## Inventory

| Service | Purpose | Config |
|---|---|---|
| Google BigQuery | data store + `ML.EXPLAIN_PREDICT` model serving | `GOOGLE_CLOUD_PROJECT`, `BQ_DATASET` (default `a4i_climate`), `BQ_LOCATION` (default `US`), `BQML_MODEL` (default `offset_model`) |
| Vertex AI / Gemini | LLM reasoning | `HEAT_AGENT_MODEL` (default `gemini-2.5-flash`), `HEAT_VERTEX_LOCATION` (default `us-central1`), service-account auth |
| Google Maps JavaScript API | client-side heat map | `GOOGLE_MAPS_API_KEY`, no server-side use |
| Google Cloud Storage | pre-staged data snapshot (fallback loader only) | public read of `gs://class-demo/a4i-2026/challenge-1-walkability`, no credentials needed beyond ambient `gcloud`/`bq` auth |

## Rules

- ✅ Add any new external service's config as an environment variable read through `config.py:load_settings()`, with a sane default where one exists, following the existing `Settings` dataclass pattern.
- ✅ Restrict any new Google Maps / client-exposed API key to the specific API and the app's own URLs, per `agent/README.md`'s existing guidance.
- ✅ Access BigQuery only through `bq.run_query()` (see `.claude/rules/bigquery.md`) — never instantiate a second `bigquery.Client`.
- ❌ Never read a new external-service credential/key directly in route or tool code — add it to `config.py` first.

## Local/dev behavior

No emulator for BigQuery or Vertex AI — local dev uses a real GCP project via Application
Default Credentials. Tests never call any of these services (see `.claude/rules/testing.md`).

## References

- `CLAUDE.md` — hub
- `.claude/rules/bigquery.md` — BigQuery access pattern
- `.claude/rules/security.md` — secret handling for these integrations

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
