# Governance Audit — 2026-10-27

**Repo:** `Challenge01---Climate-Resilience`
**Rubric used:** coe-tier-rubric v1.30.0 (via `get_tier_generation_plan`/`get_governance_audit_skill`
in this bootstrap session — this run's conversation also holds an earlier fetch of v1.6.1;
where the two differ, v1.30.0's required-gate set is treated as current and is what this audit
scores against: Bronze required B1+B2+B3+B8+B12; Silver required S1+S8; Gold required G2+G3+G4).

## Executive Summary

This was a **first bootstrap run** on a greenfield, 2-commit hackathon repo with no prior
governance layer. All three tiers' **required** gates are met. Several **advisory** gates are
also met (secret scanning, pre-commit hook, 8 skills, dependency bot, codebase walkthrough).
Two advisory gates are honestly left open (B11 Makefile/README Quick Start cross-reference,
S5 CI coverage threshold) rather than padded to look complete — see `bootstrap-findings.md`.

**Tier achieved: 🥇 Gold**

## Bronze Scorecard

| Gate | Description | Required? | Status | Evidence |
|---|---|---|---|---|
| B1 | Instruction hub present | ✅ Required | ✅ PASS | `CLAUDE.md` — self-contained, substantive, lists every `.claude/rules/` file |
| B2 | Security guidance present | ✅ Required | ✅ PASS | `CLAUDE.md`'s `## Security` section (>80 chars, repo-specific); full detail in `.claude/rules/security.md` scope note (security content actually lives as a section of the hub, per the self-contained shape) |
| B3 | Domain instruction file present | ✅ Required | ✅ PASS | 5 real domain spokes: `adk-agent.md`, `bigquery.md`, `api.md`, `integrations.md`, `observability.md` |
| B4 | Secret scanning in CI | ⚪ Advisory | ✅ PASS | `.github/workflows/secret-scan.yml` (gitleaks CLI) |
| B6 | Pre-commit hook present | ⚪ Advisory | ✅ PASS | `hooks/pre-commit`, executable |
| B8 | Valid frontmatter on instruction files | ✅ Required | ✅ PASS | Verified by grep: every `.claude/rules/*.md` has `description`+`paths`, zero `applyTo` occurrences |
| B10 | CLAUDE.md/AGENTS.md present, routed through instruction hub | ⚪ Advisory | ✅ PASS | Both present; `CLAUDE.md` is the hub itself in this shape, `AGENTS.md` points at it |
| B11 | Makefile targets match README Quick Start | ⚪ Advisory | ⚠️ OPEN | `Makefile` has real targets, but the root `README.md` is the challenge's own instructions document and has no "Quick Start" section referencing `make` — out of this run's scope to restructure (see `bootstrap-findings.md`) |
| B12 | `docs/adr/` + `docs/governance/` both exist | ✅ Required | ✅ PASS | Both created this run |

**Bronze: all required gates pass.**

## Silver Scorecard

| Gate | Description | Required? | Status | Evidence |
|---|---|---|---|---|
| S1 | Full instruction set (hub + security + 2+ domain files) | ✅ Required | ✅ PASS | 5 domain spokes, well above the 2-file minimum |
| S2 | 3+ skills incl. security + review checklist | ⚪ Advisory | ✅ PASS | 8 skills: `security`, `review-checklist`, `testing`, `deployment`, `database`, `bigquery-ml-modeling`, `adk-agent-design`, `monitoring` |
| S3 | Bootstrap findings documented | ⚪ Advisory (mandatory file per tier plan) | ✅ PASS | `bootstrap-findings.md` this run |
| S4 | 3+ ADR documents | ⚪ Advisory | ✅ PASS | `ADR-001`, `ADR-002`, `ADR-003` |
| S5 | Test coverage gates in CI | ⚪ Advisory | ⚠️ OPEN | No coverage-threshold enforcement added — out of scope (would require editing `agent/`'s CI setup, a team decision; see `bootstrap-findings.md`) |
| S6 | KTLO audit script present | ⚪ Advisory | ✅ PASS | `scripts/modernization-audit.sh`, executable |
| S7 | Phase T / Test Health, no red rows | ⚪ Advisory | ✅ PASS | See Test Health section below — no red rows; two known gaps documented, not hidden |
| S8 | Substantive AI-assisted-dev guide | ✅ Required | ✅ PASS | `docs/training/ai-assisted-dev-guide.md`, linked from root `README.md` |
| S9 | Codebase walkthrough | ⚪ Advisory | ✅ PASS | `docs/architecture/codebase-walkthrough.html`, linked from root `README.md` (Phase 10) |
| S10 | Automated dependency updates | ⚪ Advisory | ✅ PASS | `.github/dependabot.yml` (pip + github-actions ecosystems) |

**Silver: all required gates pass.**

## Gold Scorecard

| Gate | Description | Required? | Status | Evidence |
|---|---|---|---|---|
| G1 | 3+ (plan text: 8+) substantive skills | ⚪ Advisory | ✅ PASS | 8 skills (see S2) |
| G2 | Custom domain agent defined | ✅ Required | ✅ PASS | `.claude/agents/heat-planner-reviewer.md` |
| G3 | KTLO audit workflow in CI | ✅ Required | ✅ PASS | `.github/workflows/modernization-audit.yml` (monthly schedule + 120-day overdue issue creator) |
| G4 | Recent bootstrap audit run (within 120 days) | ✅ Required | ✅ PASS | `docs/modernization/runs/2026-10-27/` — dated today |
| G5 | Bootstrap cadence (within 30 days) | ⚪ Advisory | ✅ PASS | Same run, dated today |
| G6 | Instruction files pass CoE accuracy review | ⚪ Manual | ➖ N/A | Requires human CoE sign-off; not scoreable by this bootstrap |
| G7 | AI coding-tool engagement above threshold | ⚪ Manual | ➖ N/A | Requires CoE engagement data; not scoreable by this bootstrap |
| G8 | Artifact contributed back to CoE | ⚪ Manual | ➖ N/A | Not applicable to a hackathon team repo |
| G9 | Version-drift detection with auto-PR | ⚪ Planned | ⚠️ STUB | `.github/workflows/version-drift-detection.yml` created, but only checks this repo's own stamp is present — does not yet fetch the canonical upstream source to detect real drift (documented limitation in the workflow's own comment, matching the gate's own "planned" status) |

**Gold: all required gates pass. Tier achieved: 🥇 Gold.**

## Test Health

| Layer | Status | Notes |
|---|---|---|
| Unit (tools) | ✅ Healthy | `test_tools.py` — validation, success, error paths covered for every tool |
| Agent wiring | ✅ Healthy | `test_agent_wiring.py` — routing and tool-set assertions |
| Integration (agent loop) | ✅ Healthy | `test_service.py` — real ADK loop via `ScriptedLlm`, no live Gemini call |
| API | ✅ Healthy | `test_api.py` — FastAPI `TestClient`, status codes and error mapping |
| Map/graph data | ✅ Healthy | `test_mapdata.py` — pure-function graph building + endpoint error mapping |
| Known gaps (not red, just open) | ⚠️ Noted | `config.py:load_settings()` has no direct unit test; the step-budget truncation path in `callbacks.py` is reached only indirectly |

No severity-red rows — this is a healthy, if young, test suite.

## Dependency / Version Notes

`agent/requirements.txt` and `requirements-dev.txt` use open lower-bound ranges
(`google-adk>=2.12,<3`, `google-cloud-bigquery>=3.40`, `fastapi>=0.115`, `uvicorn[standard]>=0.34`,
`pytest>=8`, `httpx>=0.27`) with no lockfile. No specific CVE was identified against these
ranges during this audit (no live CVE/NVD lookup was performed as part of this governance
bootstrap — this is a documentation/process gap note, not a claim that a scan was run and
came back clean). Recorded as concern C2 in `facts/concerns.md`.

## Top 3 Recommended Next Actions

1. Decide whether to add a `pytest`-on-PR CI workflow (B11/S5-adjacent, but really an
   application-CI decision, not a governance-file gap).
2. Build the equity-audit output `docs/adr/ADR-003` leaves as an open follow-up — the root
   `README.md` calls this the most-skipped, highest-value move available in this challenge.
3. Re-run this bootstrap's Phase 9 (or the full run) before the 120-day G4 window closes, or
   sooner if the team wants to keep the 30-day G5 cadence.
