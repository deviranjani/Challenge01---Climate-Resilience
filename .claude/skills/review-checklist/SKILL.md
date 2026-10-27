---
name: review-checklist
description: 'This repo''s own PR review checklist for agent/heat_planner/ changes — agent routing, tool safety, test coverage, and prompt changes. Use when: reviewing a pull request or checking changed files in this repo. Trigger phrases: "review this PR", "check my changes", "look at this diff", "is this ready to merge".'
---

# Review Checklist

## When to Use This Skill

When reviewing a pull request or a local diff against `agent/heat_planner/`, `agent/tests/`,
or the data-loading scripts/notebooks in this repo.

## Prerequisites

Read `CLAUDE.md`'s Instruction Map and the specific `.claude/rules/*.md` spoke(s) the diff
touches before using this checklist — it assumes you already know those rules.

## Agent/Tool Changes

- [ ] A new tool is registered on exactly one sub-agent in `sub_agents.py`, with a tool set that stays small and non-overlapping with the sub-agent's siblings (see `.claude/rules/adk-agent.md`).
- [ ] A new tool is wrapped in `@safe_tool` and validates its inputs with `tools/_common.py` helpers.
- [ ] A new tool has a docstring ADK can use to decide when to call it (the existing tools' docstrings are the style to match — see `tools/prediction.py:79`).
- [ ] Any new or changed prompt text in `prompts.py` is reviewed as carefully as code — it's the primary safety mechanism (refusal conditions, caveats, no-invented-numbers rule).

### ✅ Correct

```python
@safe_tool
def new_tool(x: float) -> dict[str, Any]:
    """One-line purpose. Use this for <specific scenario>.

    Args: ...
    Returns: a dict with status ("ok" | "error" | "out_of_coverage") ...
    """
    x = clamp_int(x, LOW, HIGH, "x")
    ...
```

## BigQuery Changes

- [ ] Every query goes through `bq.run_query()` with parameters for LLM-/user-influenced values (see `.claude/rules/bigquery.md`).
- [ ] `ML.EXPLAIN_PREDICT`, not `ML.PREDICT`, for any model-serving change.
- [ ] `FEATURE_SQL` changes are coordinated with the data/training side — a drift here silently breaks predictions.

## Test Coverage

- [ ] Every new tool has a `test_tools.py`-style unit test (validation, success, error cases) using `fake_runner`.
- [ ] A change to agent routing or callback behavior has at least indirect coverage via `test_service.py`'s `ScriptedLlm` pattern.
- [ ] `cd agent && .venv/bin/python -m pytest` passes locally before requesting review.

## API Changes

- [ ] New/changed request bodies are Pydantic models with explicit length/range bounds (see `.claude/rules/api.md`).
- [ ] Blocking calls use `asyncio.to_thread()`.
- [ ] Domain errors map to the right HTTP status (503 for `AgentError`/`ToolError`), not a generic 500.

## Equity / Framing (specific to this challenge)

- [ ] No new feature or prompt rule reintroduces race/ethnicity as a model input or a stated reasoning factor — see `docs/adr/ADR-003-exclude-race-as-model-input.md`.
- [ ] Any change to the ranking/priority logic (`score_sites`) is checked against the equity-audit intent in the root `README.md` (does the change make vulnerable tracts more or less likely to be surfaced, and is that intentional?).

## Checklist

Before approving:

- [ ] All items above relevant to the diff are checked
- [ ] Tests pass
- [ ] No governance file (`CLAUDE.md`, `.claude/rules/*`) needs an update the PR didn't make

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
