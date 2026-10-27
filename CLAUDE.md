---
description: "Repository knowledge hub for Claude Code: purpose, local setup, commands, security, concerns."
applyTo: "**"
---

# Challenge01---Climate-Resilience — Claude Code Instructions

## Purpose

Agents for Impact 2026, Challenge 1 (Community Climate Resilience: Urban Heat) hackathon
repo. Loads NOAA Heat Watch street-level temperature readings, GHCN-Daily station history,
and ACS census-tract demographics into BigQuery, trains a BigQuery ML offset model, and
serves a Google ADK "heat planner" agent (`agent/heat_planner/`) that a city planner can
hold a conversation with — predicting heat risk at any coordinate via `ML.EXPLAIN_PREDICT`,
explaining why, reporting historical frequency, and describing who lives nearby.

## Local Setup

- Prerequisites: Python 3.11, `gcloud` CLI with Application Default Credentials, a GCP
  project with the `a4i_climate` BigQuery dataset already loaded.
- Required local services: none beyond BigQuery/Vertex AI in your GCP project (no emulator).
- Required local config files: `agent/.env` (copy `agent/.env.example`; set at minimum
  `GOOGLE_CLOUD_PROJECT`). Never commit `.env`.
- Setup sequence: `cd agent && cp .env.example .env && gcloud auth application-default login && ./run.sh`
- Start sequence: `./run.sh` (serves `http://127.0.0.1:8080`), or `adk web .` for ADK's own dev UI.
- Validation: `curl http://127.0.0.1:8080/api/health` → `{"ok": true, ...}`.
- Troubleshooting: none documented beyond `agent/README.md`.

## Local Commands

| Task | Command |
|---|---|
| Validate environment | `make check` |
| Run tests | `cd agent && .venv/bin/python -m pytest` (or `make test-agent`) |
| Start locally | `cd agent && ./run.sh` (or `make dev-agent`) |
| Load BigQuery data | `bash scripts/load.sh <city>` |

## Instruction Map

| Work type | Read this file | Applies to |
|---|---|---|
| Security, secrets, SQL safety, GCP service-account scope | `.claude/rules/security.md` | all code |
| Tests, mocks, fixtures | `.claude/rules/testing.md` | `agent/tests/**` |
| ADK agent/sub-agent/tool/callback design | `.claude/rules/adk-agent.md` | `agent/heat_planner/agent.py`, `sub_agents.py`, `callbacks.py`, `context.py`, `prompts.py`, `service.py` |
| BigQuery client, query safety, BQML/`ML.EXPLAIN_PREDICT` pattern | `.claude/rules/bigquery.md` | `agent/heat_planner/bq.py`, `agent/heat_planner/tools/**` |
| FastAPI routes, request/response shape, error mapping | `.claude/rules/api.md` | `agent/heat_planner/api.py` |
| External services (BigQuery, Vertex AI, Google Maps) inventory | `.claude/rules/integrations.md` | config and client code |
| Logging, what observability exists and what doesn't | `.claude/rules/observability.md` | `agent/heat_planner/**` |

## Uncovered Patterns

If a coding pattern is not addressed by any file above, do not invent one from training
data. Flag the gap with `// TODO: No governance rule covers this pattern — review with team`,
follow the nearest existing pattern in `agent/heat_planner/`, prefer the standard library,
and avoid adding a new dependency to `agent/requirements.txt` without discussion — this repo
ships to a live hackathon judging deadline.

## Governance Review

After a code change and passing tests, check it against this file and the relevant
`.claude/rules/*.md` spoke(s) above. If you introduced a pattern not covered by any
spoke, violated an existing rule with explicit user approval, or found/resolved a concern,
end your response with a `## Governance Review` section naming the file, what changed, and
the proposed instruction update — do not edit instruction files without explicit approval.
If nothing applies: `No governance updates needed`.

## Security

Full detail: `.claude/rules/security.md`. Summary: secrets (`GOOGLE_CLOUD_PROJECT`,
`GOOGLE_MAPS_API_KEY`, etc.) are read from environment only, never hardcoded; every BigQuery
call goes through one function (`bq.run_query`) using fixed SQL plus `ScalarQueryParameter` —
the LLM can never inject SQL; every tool is wrapped in `safe_tool` so exception internals
never reach the model or the client; `maximum_bytes_billed` caps cost per query.

## Concerns

- No CI existed before this bootstrap run — `.github/workflows/modernization-audit.yml`,
  `secret-scan.yml` and `governance-gate.yml` are added by this run, but a dedicated
  `pytest`-on-PR workflow is a separate, open team decision.
- `agent/requirements.txt` / `requirements-dev.txt` use open version ranges, no lockfile.
- No structured observability: no correlation IDs, metrics, or tracing — see
  `.claude/rules/observability.md` for exactly what does and doesn't exist.
- `mapdata.py`'s in-process cache does not share state across Cloud Run instances if the
  service is ever scaled beyond `--min-instances 1`.
- Full detail and evidence: `docs/governance/bootstrap-runs/2026-10-27/facts/concerns.md`.

## Current Gaps

- No CI runs `pytest` automatically on PR (team decision, not added by this bootstrap).
- See `docs/modernization/runs/2026-10-27/bootstrap-findings.md` for the full list.

## Future State

- No active modernization target recorded — this is a 2-commit hackathon repo, not a
  legacy system being migrated.

## Skills

- `.claude/skills/security/SKILL.md` — security review checklist for this repo's secret/SQL patterns
- `.claude/skills/review-checklist/SKILL.md` — this repo's PR review checklist
- `.claude/skills/testing/SKILL.md` — how to write and run tests here (mocking BigQuery/ADK)
- `.claude/skills/deployment/SKILL.md` — Cloud Run deploy steps and service-account scopes
- `.claude/skills/database/SKILL.md` — BigQuery dataset/table/model reference
- `.claude/skills/bigquery-ml-modeling/SKILL.md` — the offset model, feature parity, `ML.EXPLAIN_PREDICT`
- `.claude/skills/adk-agent-design/SKILL.md` — adding or changing a sub-agent/tool
- `.claude/skills/monitoring/SKILL.md` — what logging exists, how to read the per-request tool trace

## Key Docs

- `docs/adr/` — architecture decision records
- `docs/ARCHITECTURE.md` + `docs/architecture.mmd` — system diagram
- `docs/architecture/codebase-walkthrough.html` — interactive architecture walkthrough
- `docs/training/ai-assisted-dev-guide.md` — how this team uses AI tools in this repo
- `docs/modernization/runs/` — bootstrap and audit run history

## References

- `.claude/rules/security.md`, `.claude/rules/testing.md`, `.claude/rules/adk-agent.md`,
  `.claude/rules/bigquery.md`, `.claude/rules/api.md`, `.claude/rules/integrations.md`,
  `.claude/rules/observability.md`
- `AGENTS.md` — entry point for non-Claude AI tools
- `docs/adr/`

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper, Gold-tier run |
