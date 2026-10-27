# Heat Planner Agent — 3-Track Dallas Heat Resilience Specification

A Google ADK multi-agent system and single-page web UI built over the BigQuery ML `offset_model` (`ML.EXPLAIN_PREDICT`), NOAA GHCN 7-year station history (`station_daily_temps`), and US Census ACS tract demographics (`tract_demographics`).

---

## 1. Three-Track Decision Framework & Guardrails

The agent enforces hard operational guardrails in code (`heat_planner/config.py` and `heat_planner/tools/tracks.py`) and in system instructions (`heat_planner/prompts.py`):

| Track | Horizon | Tool Function | Hard Guardrails & Operational Rules | Scoring & Grounding |
|---|---|---|---|---|
| **Track 1 — Today** | Immediate Emergency Dispatch | `dispatch_today_fleet(hydration_trucks=20, wellness_units=10)` | **Max 20 Hydration Trucks** across Dallas (`HEAT_MAX_HYDRATION_TRUCKS=20`). Allocates **1–3 trucks per zone** scaled by heat offset and population (`sum(trucks_assigned) <= 20`). Co-dispatches **Dallas Fire-Rescue engines** (`fire_engine_support=True`) for hydrant misting when `predicted_offset_f >= +2.5°F` or `>= 2` trucks are assigned.<br>**Max 10 Mobile Wellness Check Units** (`HEAT_MAX_WELLNESS_UNITS=10`). | **Hydration**: $0.55 \cdot z_{\text{heat}} + 0.30 \cdot z_{\text{no\_car}} + 0.15 \cdot z_{\text{age}}$<br>**Wellness Checks**: $0.35 \cdot z_{\text{heat}} + 0.25 \cdot z_{\text{age}} + 0.20 \cdot z_{\text{no\_car}} + 0.20 \cdot z_{\text{older\_housing}}$ |
| **Track 2 — This Budget Cycle** | Capital Infrastructure | `recommend_cooling_centers(max_centers=3)` | **Max 3 Permanent Cooling Centers** (`HEAT_MAX_COOLING_CENTERS=3`).<br>**Nearest Public Library Supplementary Cooling**: Every recommended site is paired via Haversine distance with its closest **Dallas Public Library branch** (`DALLAS_LIBRARIES`) for overflow/immediate cooling. | **Cooling Benefit**: $0.40 \cdot z_{\text{heat}} + 0.25 \cdot z_{\text{no\_car}} + 0.20 \cdot z_{\text{poverty}} + 0.15 \cdot z_{\text{pop}}$, contextualized with 7-year `station_daily_temps` ($\ge 100^\circ\text{F}$ days/year). |
| **Track 3 — This Decade** | 10-Year Urban Forestry | `plan_tree_canopy(top_n=5)` | **Max 10 Canopy Priority Zones** (`HEAT_MAX_CANOPY_ZONES=10`).<br>**Modeling Guardrail**: Explicitly states that `ML.EXPLAIN_PREDICT` diagnoses *where* peak afternoon heat is worst and *why* (built-environment/surface drivers), rather than simulating post-planting temperatures. | **Canopy Priority**: $0.45 \cdot z_{\text{heat}} + 0.25 \cdot z_{\text{older\_housing}} + 0.15 \cdot z_{\text{pop}} + 0.15 \cdot z_{\text{poverty}}$ + top `ML.EXPLAIN_PREDICT` feature attributions. |

---

## 2. Architecture

```
browser (ui/static)  ->  POST /api/chat  ->  service.run()  ->  ADK Runner (fresh per request)
                                                   heat_planner (root: routes, writes the final answer)
                                                   |- prediction_analyst  predict_heat_offset, rank_response_sites,
                                                   |                      dispatch_today_fleet (Track 1),
                                                   |                      recommend_cooling_centers (Track 2),
                                                   |                      plan_tree_canopy (Track 3)
                                                   |- history_analyst     heat_frequency
                                                   `- community_analyst   community_profile
```

| Piece | Where | Notes |
|---|---|---|
| Root agent and routing | `heat_planner/agent.py`, `prompts.py` | Enforces 3-track guardrails; never invents numbers; refuses other cities and made-up coordinates |
| Sub-agents | `heat_planner/sub_agents.py` | `prediction_analyst` (ML + Track 1/2/3 tools), `history_analyst`, `community_analyst` |
| Track 1 / 2 / 3 tools | `heat_planner/tools/tracks.py` | Fleet scaling, fire-engine co-dispatch, 3 cooling centers + nearest library, decade tree canopy |
| Point & general ranking tools | `heat_planner/tools/prediction.py` | `predict_heat_offset` and `rank_response_sites` via `ML.EXPLAIN_PREDICT` |
| Station & community tools | `heat_planner/tools/history.py`, `community.py` | 7-year threshold frequency (`station_daily_temps`) and radius demographics (`tract_demographics`) |
| BigQuery layer | `heat_planner/bq.py` | Parameterized read-only queries, 1 GB per-query byte cap, 500-row cap |
| Callbacks & UI cards | `heat_planner/callbacks.py`, `ui/static/app.js` | Step budget, tool trace, and interactive UI cards for all 3 tracks |

`predict_heat_offset`, `rank_response_sites`, `dispatch_today_fleet`, `recommend_cooling_centers`, and `plan_tree_canopy` call **`ML.EXPLAIN_PREDICT`** on `offset_model`.
The feature columns are defined in `tools/prediction.py` (`FEATURE_SQL`). They must match the training table; if the data lane changes features, update `FEATURE_SQL` in one place.

Tool failures never raise to the model: each tool returns `{"status": "error" | "out_of_coverage", ...}` and the UI renders it as a notice.

---

## 3. Run Locally

```bash
cp .env.example .env          # set GOOGLE_CLOUD_PROJECT
gcloud auth application-default login
./run.sh                      # http://127.0.0.1:8080
adk web .                     # alternative: ADK dev UI serving heat_planner.root_agent
```

---

## 4. Test

```bash
uv run --with-requirements agent/requirements-dev.txt pytest agent/tests -v
```

All 30 unit and integration tests mock BigQuery and drive the real ADK loop with a scripted model (no live BigQuery or Vertex AI calls required).

---

## 5. Deploy to Cloud Run

```bash
gcloud run deploy heat-planner --source . --region us-central1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project>,BQ_DATASET=a4i_climate --min-instances 1
```

The runtime service account requires `BigQuery Job User`, `BigQuery Data Viewer` on the dataset, and `Vertex AI User`.
