# Bootstrap Findings — 2026-10-27

Run: orange-lens-ai-bootstrapper v3.4.1 (coe-tier-rubric v1.30.0), targeting Gold tier.
Repo: `Challenge01---Climate-Resilience`. Pre-filled from
`docs/governance/bootstrap-runs/2026-10-27/facts/`.

## What was found (Phase 0/1)

- Hackathon starter kit for Agents for Impact 2026, Challenge 1 (Urban Heat). Python 3.11,
  Google ADK agent (`agent/heat_planner/`) over BigQuery + BigQuery ML, FastAPI + static UI,
  pytest test suite (BigQuery and ADK mocked throughout, no live calls).
- No governance layer existed before this run: no `.github/instructions/`, no `.claude/`, no
  `CLAUDE.md`/`AGENTS.md`, no `docs/adr/`, no CI/CD, no `Makefile`.
- 2 commits total, last dated 2026-10-27 — effectively a greenfield repo with no accumulated
  legacy debt in the usual modernization sense.
- `ai_tool_target` determined to be `none_detected` (no Claude/Copilot signal anywhere in the
  repo or git history) → treated as `claude` per the repo-discovery skill's default, producing
  a self-contained `CLAUDE.md` + `.claude/rules/` shape rather than hub-and-spokes.
- `agent/.env.example` could not be read under this bootstrap session's directory permission
  settings. Worked around by cross-checking every env var name against `config.py:load_settings()`,
  which is the authoritative source for defaults — no fact in `.claude/rules/security.md` or
  `integrations.md` is unverified as a result, but this is recorded here for transparency.

## What was generated

40-file Gold-tier plan, adapted to the self-contained shape (`get_tier_generation_plan('gold', 'claude')`):

- `CLAUDE.md`, `AGENTS.md`
- 6 `.claude/rules/*.md` spokes: `testing.md`, `adk-agent.md`, `bigquery.md`, `api.md`, `integrations.md`, `observability.md`
- 8 `.claude/skills/*/SKILL.md`: `security`, `review-checklist`, `testing`, `deployment`, `database`, `bigquery-ml-modeling`, `adk-agent-design`, `monitoring`
- 1 `.claude/agents/heat-planner-reviewer.md` custom domain agent
- 3 ADRs (`docs/adr/ADR-001` through `ADR-003`) + `docs/adr/README.md` index
- `docs/patterns.md`, `docs/testing.md`, `docs/ARCHITECTURE.md`, `docs/architecture.mmd`
- `docs/training/ai-assisted-dev-guide.md`
- `docs/architecture/codebase-walkthrough.html` (Phase 10)
- `Makefile`, `CONTRIBUTING.md`, `.github/pull_request_template.md`, `hooks/pre-commit` (executable)
- `.github/workflows/secret-scan.yml`, `governance-gate.yml`, `modernization-audit.yml`, `version-drift-detection.yml`
- `.github/dependabot.yml`
- `scripts/modernization-audit.sh` (executable)
- This run's facts/findings/AUDIT files; one new section appended to the root `README.md`

## Gaps acted on vs. left open (honesty over padding)

| Gap | Decision | Why |
|---|---|---|
| No dedicated `pytest`-on-PR CI workflow | **Left open** | Out of this governance bootstrap's scope — `.github/workflows/modernization-audit.yml` runs the governance audit script, not the app test suite. Adding a test-on-PR workflow is an application-CI decision for the team, not a governance-file generation task. Recorded in `CLAUDE.md`'s Concerns and here, not silently added. |
| `agent/requirements.txt`/`requirements-dev.txt` use open version ranges, no lockfile | **Left open** | A dependency-pinning change touches `agent/` application files, which were explicitly out of scope for this run. Recorded as a concern (C2 in `facts/concerns.md`). |
| No structured observability (correlation IDs, metrics, tracing) | **Left open** | Documented accurately in `.claude/rules/observability.md` rather than inventing a pattern that doesn't exist. Not a blocking gap for any CoE gate. |
| The root README's "equity audit" (comparing recommended-site demographics to the city average) is described in prompts/ADR-003 as a design principle, but is **not yet built as a dedicated tool/output** in `agent/heat_planner/` | **Left open, explicitly** | `docs/adr/ADR-003-exclude-race-as-model-input.md`'s Follow-up table marks this "in review," not "decided — implemented." This is an application feature gap, not a governance-file gap, and this run does not claim otherwise. |
| `mapdata.py`'s in-process cache does not share state across multiple Cloud Run instances | **Left open** | Documented in `docs/patterns.md` and `facts/concerns.md` (C5); an application-code decision, not a governance gate. |
| S1 / B3 domain-topic count | **Satisfied, not padded** | 4 real `.claude/rules/` domain spokes exist beyond `testing.md` (project-level) — `adk-agent.md`, `bigquery.md`, `api.md`, `integrations.md`, `observability.md` — well above B3's 1 and S1's 2 minimum. None is a placeholder; each cites specific file/line evidence. |

No empty or placeholder files were created to artificially satisfy a gate count (B3/S1 domain
files, S2/G1 skill count) — verified by grep for template placeholder tokens across every
generated file (clean) as part of Phase 8 verification.

## Recommendations

1. Decide, as a team, whether to add a `pytest`-on-PR CI workflow (distinct from the
   governance/modernization-audit workflow added by this run).
2. Build the explicit equity-audit output (`docs/adr/ADR-003`'s open follow-up item) if the
   team wants this to be a scored differentiator in judging — the root `README.md` flags it as
   "the most interesting conversation available in this challenge and most teams will skip it."
3. Review `docs/governance/bootstrap-runs/2026-10-27/facts/concerns.md` for the full concern
   list (C1–C5) and triage with the team.
4. Re-run this bootstrap (or at least Phase 9's audit) if the repo is still active within 30
   days (Gold G5 advisory cadence) or 120 days (Gold G4 required cadence).
