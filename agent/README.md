# Heat Planner agent

A Google ADK agent tree and a small chat UI over the BigQuery ML heat-offset model.
Built for the **Today** track: where to send hydration trucks and wellness checks first.

## Architecture

```
browser (ui/static)  ->  POST /api/chat  ->  service.run()  ->  ADK Runner (fresh per request)
                                                   heat_planner (root: routes, writes the final answer)
                                                   |- prediction_analyst  predict_heat_offset, rank_response_sites
                                                   |- history_analyst     heat_frequency
                                                   `- community_analyst   community_profile
```

| Piece | Where | Notes |
|---|---|---|
| Root agent and routing | `heat_planner/agent.py`, `prompts.py` | Never invents numbers; refuses other cities and made-up coordinates |
| Sub-agents | `heat_planner/sub_agents.py` | One small tool set each, so routing is unambiguous |
| Tools | `heat_planner/tools/` | Fixed SQL with query parameters; the model never writes SQL |
| BigQuery layer | `heat_planner/bq.py` | One client, a per-query byte cap, row cap, logging |
| Callbacks | `heat_planner/callbacks.py` | Step budget, tool trace, tool results turned into UI cards |
| API and UI | `heat_planner/api.py`, `ui/static/` | Stateless: the browser sends the history |

`predict_heat_offset` and `rank_response_sites` call **`ML.EXPLAIN_PREDICT`** on `offset_model`.
The feature columns are built in `tools/prediction.py` (`FEATURE_SQL` and the two queries). They
must match the training table; if the data lane changes features, change them there only.

Tool failures never raise to the model: each tool returns `{"status": "error" | "out_of_coverage", ...}`
and the UI draws it as a notice. Locations outside the measured area are refused before the model is called.

## What it solves: three tracks

The page opens on a track. Each shows a specific problem card, the BigQuery data behind it, any live API used as a complement, and
what the analysis cannot do. Only the panes that belong to the chosen track are shown.

| Track | Decision | What we compute (all from BigQuery) | Shown |
|---|---|---|---|
| **Today** (emergency response) | Where hydration trucks, wellness checks and extended library hours go first | Areas ranked by predicted heat plus who is least able to cope, with a reason per stop | Map, dispatch list, tomorrow's heat (NWS forecast, a complement), equity audit |
| **Budget cycle** (cooling centers) | Where permanent cooling centers go | Sites that cover the most heat-exposed, vulnerable people within walking distance without double counting; how often the city reaches 100 F | Map with walking radii, centers, heat-days tracker, equity audit, draft council proposal |
| **This decade** (tree planting) | Where planting or cool pavement should start | Areas ranked by people x excess heat x poverty; what drives each area's heat | Map, planting priorities, tract graph, equity audit |

The logic is in `heat_planner/tracks.py` as pure functions, so every number traces to a formula. Costs, land use, tree canopy and
pavement are not in the data, and the app says so instead of estimating them.

## Areas, not coordinates

People ask about "Oak Cliff" or "75215". Structure comes from BigQuery: `tract_areas` maps every census tract to its ZIP code and city
(`bash scripts/build_areas.sh`, from US Census ZIP boundaries). Names come from Google Maps Platform, live: reverse geocoding labels each
tract with its neighbourhood, and Places text search turns a typed name into map bounds. Google content is held in memory for an hour
and never stored; the server authenticates with its own service account, so there is no extra key. Both APIs
(`geocoding-backend`, `places`) must be enabled. OpenStreetMap is not used: its ODbL licence is excluded by the challenge's data rules.

## Panes

| Pane | What it shows | Data |
|---|---|---|
| Problem card and trackers | The specific problem, data used, limits, four key numbers | `/api/tracks`, per-track endpoints |
| Map | Google Maps (map, satellite, aerial, 3D), heat surface, predicted offset per area, the track's decision, walking radii | `/api/map/points`, `/api/map/tracts` |
| Decision list | Ranked areas with the reason for each, controls, "Draft proposal" | `/api/today`, `/api/budget`, `/api/trees`, `/api/proposal` |
| Who this reaches | Equity audit of the chosen areas against the city (race is never an input) | in each decision |
| Tomorrow's heat (Today) | NWS 7-day forecast and a scenario high; expected temperature = scenario + predicted offset | `/api/forecast` |
| Heat-days tracker (Budget) | Days a year at 95/100/105 F and the trend | `/api/history` |
| Tract graph (This decade) | Neo4j-style graph of areas linked to heat, poverty, car-access and age groups | `/api/graph` |

## Customer-facing: nothing about the stack is shown

The page does not name the models, the voice API, BigQuery ML or how the app is built, the assistant is instructed never to,
`/api/health` returns only `{"ok": true}`, and API docs (`/api/docs`) are off. Technical details for judges and engineers live here
in this README and in the pitch deck, not in the product.

## Models (engineering notes)

| Use | Model | Location |
|---|---|---|
| Specialist agents (chat answers) | `gemini-3.8-flash` (`HEAT_AGENT_MODEL`) | `global` |
| Draft proposals | `gemini-4-argon`, thinking level LOW (`HEAT_PROPOSAL_MODEL`) | `global` |
| Root agent (routing) | `gemini-3.8-flash` | `global` |
| Speech to text | `gemini-live-2.5-flash-native-audio` | `us-central1` |

`gemini-4-argon` is slow: measured from the live logs, its calls had a median of 9 s and 23 s with a p90 of about 65 s, so chat
uses `gemini-3.8-flash` (about 3 s per call) and Argon is kept for drafting proposals, where a longer wait is fine. Set
`HEAT_AGENT_MODEL`, `HEAT_ROUTER_MODEL` or `HEAT_PROPOSAL_MODEL` to change any of them. Only tracts inside the measured area are scored: far outside it the model's
squared-coordinate features extrapolate to tens of degrees. Census "not available" codes (-666666666) are treated as missing.

## Voice

The microphone button streams 16 kHz PCM over a same-origin WebSocket (`/api/live`) to the server, which holds the
Gemini Live session, so no credentials reach the browser. The transcript appears as you speak and is sent as your
question when you stop (or after 1.8 s of silence). Esc cancels. Sessions are capped at 60 s and 4 at a time.

The Maps key is read from `GOOGLE_MAPS_API_KEY`; restrict it to the Maps JavaScript API and Map Tiles API and to the
app's URLs (Google does not accept port wildcards, so list each local port).

## Run it

```bash
cp .env.example .env          # set GOOGLE_CLOUD_PROJECT
gcloud auth application-default login
./run.sh                      # http://127.0.0.1:8080
adk web .                     # alternative: ADK's own dev UI, serves heat_planner.root_agent
```

## Test

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The tests mock BigQuery and drive the real ADK loop with a scripted model. They do not call
BigQuery or Vertex AI.

## Deploy to Cloud Run

```bash
gcloud run deploy heat-planner --source . --region us-central1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project>,BQ_DATASET=a4i_climate --min-instances 1
```

The service account needs `BigQuery Job User`, `BigQuery Data Viewer` on the dataset, and
`Vertex AI User`. Add `--allow-unauthenticated` only for a throwaway demo project.
