# Phase 1 facts — integrations inventory

| Integration | Type | Purpose | Config / access | Evidence |
|---|---|---|---|---|
| Google BigQuery | Data warehouse + ML serving | Stores `heat_observations`, `station_daily_temps`, `tract_demographics`; serves `offset_model` via `ML.EXPLAIN_PREDICT` | `GOOGLE_CLOUD_PROJECT`, `BQ_DATASET` (default `a4i_climate`), `BQ_LOCATION` (default `US`), `BQML_MODEL` (default `offset_model`) env vars; ADC via `gcloud auth application-default login` locally, Cloud Run service account in prod | `agent/heat_planner/bq.py`, `agent/heat_planner/config.py:27` |
| Vertex AI / Gemini | LLM | Reasoning for the ADK agent tree (root + 3 sub-agents) | `HEAT_AGENT_MODEL` (default `gemini-2.5-flash`), `GOOGLE_GENAI_USE_VERTEXAI=true` forced, `HEAT_VERTEX_LOCATION` (default `us-central1`); authenticated by the runtime service account, no API key | `agent/heat_planner/config.py:7-8`, `agent/heat_planner/agent.py` |
| Google Maps JavaScript API | Client-side mapping | Heat map + deck.gl overlay in the UI | `GOOGLE_MAPS_API_KEY` env var, served via `/api/map/config`; agent/README.md instructs restricting the key to the Maps JavaScript API and the app's own URLs (no port wildcards) | `agent/heat_planner/mapdata.py:44`, `agent/README.md` |
| Google Cloud Storage | Data snapshot source | `scripts/load.sh` headless fallback pulls a pre-staged parquet snapshot (`gs://class-demo/a4i-2026/challenge-1-walkability`) when the Colab notebook path is unavailable | Read-only, no credentials beyond ambient `gcloud`/`bq` auth | `scripts/load.sh` |
| NOAA Heat Watch / GHCN-Daily / US Census ACS | Public upstream data sources | Original data origin, pulled by `notebooks/c1_01_load_explore.ipynb` into BigQuery | Public domain / CC0 per root `README.md` | root `README.md` |

## Anti-patterns checked for and NOT found
- No direct BigQuery SDK calls scattered through tool/feature code — all routed through the single `bq.run_query()` entry point (`agent/heat_planner/bq.py`).
- No hardcoded project IDs, dataset names, or API keys — all read from environment (`config.py`, `mapdata.py`).

## Local / dev behavior
- No BigQuery emulator — local dev talks to a real project's BigQuery via Application Default Credentials (`agent/README.md` Run it section).
- Tests never touch BigQuery or Vertex AI — monkeypatched throughout (see `code-patterns.md`).
