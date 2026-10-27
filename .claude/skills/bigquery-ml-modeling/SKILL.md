---
name: bigquery-ml-modeling
description: 'How the offset_model is called and explained, and what to check before changing its feature set or prediction path. Use when: adding a feature to the model, changing predict_heat_offset or rank_response_sites, or explaining ML.EXPLAIN_PREDICT output to a user. Trigger phrases: "change the model features", "explain this prediction", "the model gives a weird number", "add a feature to the offset model".'
---

# BigQuery ML Modeling

## When to Use This Skill

When changing `agent/heat_planner/tools/prediction.py`, adding a feature to the model,
or explaining what `ML.EXPLAIN_PREDICT` output means to a user or in a PR description.

## Prerequisites

Read the root `README.md`'s "And one required differentiator: BigQuery ML" section and
`.claude/rules/bigquery.md` first.

## What the Model Predicts

An **offset** — degrees Fahrenheit a location runs hotter (+) or cooler (-) than its city's
own campaign-day average. Not a temperature, not a forecast. The root `README.md` is explicit
that misdescribing this as "it will be 106° here" is "the easiest thing in the challenge to
describe wrongly" — `prompts.py:3-8` encodes the correct framing directly in the agent's
system instruction.

## The Two Entry Points

| Function | Purpose | File |
|---|---|---|
| `predict_heat_offset(lat, lon)` | One location's predicted offset + attributions | `tools/prediction.py:78` |
| `rank_response_sites(top_n)` | Ranks all in-coverage census tracts by a blended priority score | `tools/prediction.py:207` |

Both route through `predict_all_tracts()` (`rank_response_sites`) or a direct
`ML.EXPLAIN_PREDICT` call (`predict_heat_offset`) — never `ML.PREDICT`.

## Reading `ML.EXPLAIN_PREDICT` Output

`_attributions()` (`tools/prediction.py:68`) flattens the nested `top_feature_attributions`
into `{"feature": ..., "effect_f": ...}`, sorted by absolute effect size, biggest first. This
is what lets the agent answer "why" — e.g. "+4.1 from street density, +2.8 from building age"
— rather than just a number. Always surface at least the top driver when reporting a
prediction; the root `README.md` singles this out as the required differentiator.

## `score_sites` — Priority Ranking (not a model output)

`score_sites()` (`tools/prediction.py:150`) is a **pure Python function**, not a BQML call —
it blends three z-scored signals (predicted offset 0.5, `no_vehicle_rate` 0.3, `median_age`
0.2) into one `priority_score`. This weighting is a design decision, not a model fact — if
you change the weights, say so explicitly in the PR and in any demo/pitch material, since it
directly shapes which neighborhoods rank highest (see the equity-audit framing in the root
`README.md` and `docs/adr/ADR-003-exclude-race-as-model-input.md`).

## Coverage Guard

`_within_coverage()` (`tools/prediction.py:60`) refuses a prediction outside the bounding box
of `heat_observations` (plus a small pad) **before** calling the model. Do not remove or
widen this pad casually — the comment at `prediction.py:200` is explicit that the model's
squared-coordinate features extrapolate to "tens of degrees" outside the measured roads.

## Changing the Feature Set

1. Confirm the new feature exists in both the training table (data/training lane's
   responsibility) and `tract_demographics`/`heat_observations` (if tract-derived).
2. Update `FEATURE_SQL` in `tools/prediction.py` — it is used by **both**
   `predict_heat_offset` and `predict_all_tracts`, so a change here affects both entry points.
3. Update `.claude/skills/database/SKILL.md`'s feature list to match.
4. Add/update a `test_tools.py`-style test asserting the new column appears in the generated SQL.

## Checklist

- [ ] Used `ML.EXPLAIN_PREDICT`, not `ML.PREDICT`
- [ ] Reported at least the top attribution(s), not just the predicted number
- [ ] Any ranking-weight change is called out explicitly, not silently adjusted
- [ ] A feature-set change updates `FEATURE_SQL` in one place, used by both prediction entry points

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
