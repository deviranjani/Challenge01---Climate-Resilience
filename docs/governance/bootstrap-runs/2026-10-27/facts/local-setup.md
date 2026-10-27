# Phase 1 facts — local setup

Source: `agent/README.md` ("Run it", "Test", "Deploy to Cloud Run" sections), `agent/run.sh`, `agent/Dockerfile`.

## Prerequisites
- Python 3.11 (Dockerfile base image: `python:3.11-slim`)
- `gcloud` CLI, authenticated (`gcloud auth application-default login`)
- A GCP project with the `a4i_climate` BigQuery dataset already loaded (via the root `notebooks/c1_01_load_explore.ipynb` or `scripts/load.sh`)

## Required local config
- `agent/.env` (copy of `agent/.env.example`) — at minimum `GOOGLE_CLOUD_PROJECT`; optionally overrides any var in `config.py:load_settings()`

## Setup sequence
```bash
cd agent
cp .env.example .env          # set GOOGLE_CLOUD_PROJECT
gcloud auth application-default login
./run.sh                      # creates .venv, installs requirements.txt, serves on :8080
```

## Alternative dev UI
```bash
adk web .                     # ADK's own dev UI, serves heat_planner.root_agent directly
```

## Test
```bash
cd agent
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```
Mocks BigQuery and drives the real ADK loop with a scripted model — no live BigQuery or Vertex AI calls.

## Validation
`curl http://127.0.0.1:8080/api/health` → `{"ok": true, "city": ..., "dataset": ..., "bqml_model": ..., "llm_model": ...}`

## Deploy (Cloud Run)
```bash
gcloud run deploy heat-planner --source . --region us-central1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project>,BQ_DATASET=a4i_climate --min-instances 1
```
Service account needs: `BigQuery Job User`, `BigQuery Data Viewer` (on the dataset), `Vertex AI User`.

## Troubleshooting
None documented beyond the above in `agent/README.md`.
