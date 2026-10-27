---
name: deployment
description: 'Deploy heat_planner to Cloud Run, including the required service-account scopes and the min-instances cold-start consideration. Use when: deploying the agent, changing the Dockerfile, or troubleshooting a Cloud Run deploy. Trigger phrases: "deploy this", "deploy to cloud run", "what IAM roles does this need", "the deploy failed".'
---

# Deployment

## When to Use This Skill

When deploying `agent/` to Cloud Run for the first time, redeploying after a change, or
troubleshooting a deploy/runtime permission error.

## Prerequisites

Read `agent/README.md`'s "Deploy to Cloud Run" section and `agent/Dockerfile` first — this
skill summarizes and operationalizes them.

## Deploy Command

```bash
gcloud run deploy heat-planner --source agent --region us-central1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project>,BQ_DATASET=a4i_climate --min-instances 1
```

- `--source agent` — the Dockerfile build context is the `agent/` directory, not the repo root.
- `--min-instances 1` — keeps one instance warm so the first request after an idle period
  (often the one made live during a demo/judging) doesn't pay a cold start.
- Add `--allow-unauthenticated` only for a throwaway demo project — never for anything meant to persist.

## Required IAM Roles (service account)

| Role | Why |
|---|---|
| `BigQuery Job User` | Run queries (`bq.run_query()`) |
| `BigQuery Data Viewer` (on the `a4i_climate` dataset) | Read `heat_observations`, `station_daily_temps`, `tract_demographics`, and the `offset_model` |
| `Vertex AI User` | Call Gemini via `GOOGLE_GENAI_USE_VERTEXAI=true` |

If a deploy succeeds but the agent returns `AgentError`/`ToolError` at runtime, check these
three roles first before assuming a code bug.

## Container Notes

- Base image: `python:3.11-slim` (`agent/Dockerfile:2`).
- Runs as a non-root user (`uid 10001`), per `agent/Dockerfile:9`.
- `--no-access-log` is set on uvicorn — access logs are intentionally suppressed; see
  `.claude/rules/observability.md` before assuming request-level logs exist in Cloud Logging.
- `PORT` defaults to 8080, read from the `PORT` env var Cloud Run injects automatically.

## Environment Variables to Set

See `.claude/rules/integrations.md` and `.claude/rules/security.md` for the full list; at
minimum, `GOOGLE_CLOUD_PROJECT` and `BQ_DATASET` are set explicitly in the deploy command
above — every other var in `config.py` has a usable default for this challenge's dataset.

## Known Scaling Caveat

`mapdata.py`'s in-process cache (`.claude/rules/bigquery.md`) does not share state across
instances. If you raise `--min-instances` above 1 or let the service autoscale, each
instance independently re-runs the cached BigQuery/BQML query on its own 600-second cycle —
not a correctness bug, but a cost/latency consideration worth knowing before scaling up.

## Checklist

- [ ] Deploying from `agent/` as the build context (`--source agent`), not the repo root
- [ ] `--min-instances 1` set if this will be demoed live
- [ ] Service account has all three IAM roles above
- [ ] `--allow-unauthenticated` only on a throwaway/demo project

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
