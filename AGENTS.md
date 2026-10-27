# Challenge01---Climate-Resilience — AI Agent Instructions

> **Single source of truth:** `CLAUDE.md` holds this repo's full guidance for Claude Code.
> This file is the agent-agnostic entry point for any other AI coding tool (Codex, Cursor,
> Gemini CLI, Windsurf, etc.) — it points at `CLAUDE.md` rather than duplicating its rules.

## Project Identity

A Google ADK "heat planner" agent over a BigQuery ML heat-offset model, built for the
Agents for Impact 2026 hackathon (Challenge 1: Urban Heat). See `CLAUDE.md`'s Purpose
section for the full description.

## Coding Standards Hub

- `CLAUDE.md` — read this first. It links every topic file under `.claude/rules/`.

## Stack and Runtime

- **Language:** Python 3.11
- **Agent framework:** google-adk >=2.12,<3
- **Web framework:** FastAPI >=0.115, uvicorn[standard] >=0.34
- **Data warehouse / ML:** Google BigQuery + BigQuery ML (`ML.EXPLAIN_PREDICT`)
- **Test framework:** pytest >=8, httpx >=0.27 (FastAPI `TestClient`)
- **Deployment:** Google Cloud Run (see `agent/Dockerfile`, `agent/README.md`)

## Commands

```bash
# Setup
cd agent && cp .env.example .env && gcloud auth application-default login && ./run.sh

# Test
cd agent && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest

# Deploy
gcloud run deploy heat-planner --source agent --region us-central1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project>,BQ_DATASET=a4i_climate --min-instances 1
```

## Repository Map

| Directory | Purpose |
|---|---|
| `agent/heat_planner/` | The ADK agent, BigQuery layer, FastAPI app |
| `agent/heat_planner/tools/` | Tool functions the agent calls (prediction, history, community) |
| `agent/tests/` | pytest suite, BigQuery/ADK mocked |
| `agent/ui/static/` | Chat + map + graph front end |
| `notebooks/`, `scripts/` | Data loading (notebook primary, `load.sh` headless fallback) |
| `docs/adr/` | Architecture decision records |
| `docs/modernization/runs/` | Bootstrap and audit run history |
| `.claude/rules/` | Claude Code topic instructions (see `CLAUDE.md`'s Instruction Map) |
| `.claude/skills/` | On-demand knowledge packs (see `CLAUDE.md`'s Skills list) |
| `.claude/agents/` | Custom domain agent definitions |

## Agent Operating Rules

- Read before write — understand `CLAUDE.md` and the relevant `.claude/rules/*.md` spoke before modifying code.
- Small, focused changes — one concern per commit.
- Update `agent/tests/` when behavior changes; follow `.claude/rules/testing.md`'s mocking pattern (never call live BigQuery or Vertex AI from a test).
- Never hardcode a secret, project ID, or API key — see `.claude/rules/security.md`.
- Never let a tool's exception reach the LLM unhandled — wrap it with `safe_tool` per `.claude/rules/bigquery.md`.
- Follow existing naming and structure; do not restructure `agent/heat_planner/` without discussion — this repo ships to a live hackathon judging deadline.

## Skills

See `CLAUDE.md`'s Skills section — the same 8 `.claude/skills/*/SKILL.md` packs apply here.

## Testing

- **Framework:** pytest + httpx
- **Run:** `cd agent && .venv/bin/python -m pytest`
- **Conventions:** `.claude/rules/testing.md`

## Related Documentation

- [CLAUDE.md](CLAUDE.md) — full Claude Code guidance (read this first)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture
- [docs/patterns.md](docs/patterns.md) — coding patterns
- [docs/testing.md](docs/testing.md) — test strategy
- [docs/adr/](docs/adr/) — architecture decision records
