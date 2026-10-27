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

## Workspace

The chat lives in the left panel; the right side is a workspace of panes that follows the conversation
(ask about a place and the map flies there, ask for the ranking and the tracker highlights it).

| Pane | What it shows | Data |
|---|---|---|
| Trackers | Forecast high, peak expected temperature, people in hotter tracts, top priority tract, heat days | all of the below |
| Live map | Google Maps (map, satellite, aerial, photorealistic 3D), live traffic, a deck.gl heat surface of the measured readings and the model's forecast per tract | `/api/map/points`, `/api/map/tracts` |
| Forecast and scenario | NWS 7-day forecast; pick a day or a scenario high and see expected temperature by tract | `/api/forecast` |
| Heat days tracker | Days a year at 95/100/105/110 F and whether that is changing | `/api/history` |
| Response tracker | Tracts ranked by predicted heat, households without a car and age | `/api/priority` |
| Tract graph | Neo4j-style graph of tracts linked to heat, poverty, car-access and age groups | `/api/graph` |

Expected temperature = forecast high + the model's predicted offset for a place. The forecast comes from the
National Weather Service (public domain); the model supplies only the within-city difference.

## Models

| Use | Model | Location |
|---|---|---|
| Specialist agents (answers) | `gemini-4-argon`, thinking level LOW | `global` |
| Root agent (routing) | `gemini-3.8-flash` | `global` |
| Speech to text | `gemini-live-2.5-flash-native-audio` | `us-central1` |

`gemini-4-argon` is slow by default (over a minute for a trivial prompt) because of its long default thinking;
`LOW` brings that to seconds, but calls still vary from about 4 to 60 s. Set `HEAT_AGENT_MODEL` or
`HEAT_ROUTER_MODEL` to change either. Only tracts inside the measured area are scored: far outside it the model's
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
