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
