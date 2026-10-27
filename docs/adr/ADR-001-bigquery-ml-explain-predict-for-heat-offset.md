# ADR-001 — BigQuery ML + ML.EXPLAIN_PREDICT for the heat-offset prediction

| **Status** | Done |
| --- | --- |
| **Owner** | @deviranjani |
| **Contributors** | @deviranjani |
| **Approved** | @deviranjani |
| **Due date** | 2026-Q4 (hackathon submission) |
| **Decision** | Use BigQuery ML with `ML.EXPLAIN_PREDICT` (not `ML.PREDICT`) to serve the heat-offset model, called from a dedicated agent tool |

---

## ❓ Problem statement

---

The agent has street-level temperature readings (`heat_observations`) only for the roads
NOAA Heat Watch volunteers actually drove — typically a few thousand to tens of thousands of
points per city, covering a fraction of any city's full area. A planner's real question is
almost always about a location nobody measured: "where should the three new cooling centers
go," "how hot is 4th and Marsalis." Querying `heat_observations` directly and describing the
nearest reading answers a different, weaker question, and the root README is explicit that
this is "the most common way to miss the point while appearing to hit it." Today, without a
model, the agent has no way to answer for an unmeasured location, and no way to explain *why*
a location runs hot rather than just reporting a number.

## 💡 Research insights

---

- The challenge's own framing names BigQuery ML as a required differentiator specifically
  because it lets the agent predict for locations with zero direct observations.
- `ML.EXPLAIN_PREDICT` returns per-feature attributions alongside the prediction (nested
  `top_feature_attributions`), at no extra modeling cost over `ML.PREDICT` — it is the same
  model, a different serving call.
- The feature set available per location (coordinates, distance to city center, squared
  coordinate terms, nearest-tract demographics) is cheap to compute at inference time via a
  `WITH` clause joining to `tract_demographics`, so no separate feature store is needed for
  this challenge's scope.

## 📊 Solution hypothesis

---

- An agent tool backed by `ML.EXPLAIN_PREDICT` can answer "how much hotter is location X" for
  any coordinate inside the measured area's bounding box, with a response time acceptable for
  a live chat turn (single BigQuery query, no batch job).
- Reporting the top 3–5 feature attributions alongside the number lets the agent answer "why"
  without a separate explanation step, satisfying the challenge's required differentiator.

## 🌈 Design options

| | **Option 1 — Query historical readings only** | **Option 2 ⭐️ CONFIRMED 2026-10-27 — BigQuery ML, `ML.PREDICT`** | **Option 3 — BigQuery ML, `ML.EXPLAIN_PREDICT`** |
| --- | --- | --- | --- |
| **Overview** | Agent queries `heat_observations`/`station_daily_temps` directly and reports the nearest measured reading or a regional average. | Train a BQML regression model on the offset target; serve predictions with `ML.PREDICT` for a number only. | Train the same model; serve with `ML.EXPLAIN_PREDICT` for a number **and** per-feature attributions. |
| **HLD** | ```mermaid\ngraph LR\n  A[Agent tool] --> B[heat_observations]\n  B --> C[nearest reading]\n```| ```mermaid\ngraph LR\n  A[Agent tool] --> B[ML.PREDICT offset_model]\n  B --> C[offset number]\n```| ```mermaid\ngraph LR\n  A[predict_heat_offset tool] --> B[ML.EXPLAIN_PREDICT offset_model]\n  B --> C[offset number]\n  B --> D[top-k feature attributions]\n```|
| **Link** | root `README.md` — "Your agent has to actually call the prediction" | root `README.md` — "required differentiator: BigQuery ML" | root `README.md` — "Use `ML.EXPLAIN_PREDICT` rather than `ML.PREDICT`" |
| **Benefits and risks** | ➕ Simplest to build<br>➕ No model training needed<br>➖ Cannot answer for any unmeasured location — fails the challenge's central requirement<br>➖ No "why" explanation available | ➕ Answers unmeasured locations<br>➕ Meets the BigQuery ML requirement<br>➖ Gives a number with no reason — "teams that treat explanation as a reporting step at the end finish with a number and no argument" (root README) | ➕ Answers unmeasured locations<br>➕ Gives both the number and the reason in one call, no extra cost<br>➕ Directly supports the "This decade" track's intervention recommendation use case<br>➖ Attribution parsing (`_attributions()`) adds a small amount of response-shaping code |
| **Tasks** | — (rejected) | — (rejected, superseded by Option 3) | Implemented: `tools/prediction.py:predict_heat_offset`, `:predict_all_tracts`, `:_attributions` |

## ✅ Follow up

| **Decision** | **Status** | **Next steps** |
| --- | --- | --- |
| Use `ML.EXPLAIN_PREDICT` for every model-serving tool, never `ML.PREDICT` | decided | Enforced in `.claude/rules/bigquery.md` and `.claude/skills/bigquery-ml-modeling/SKILL.md`; checked in `.claude/skills/review-checklist/SKILL.md` |
| Coverage bounding-box guard before calling the model | decided | Implemented: `tools/prediction.py:_within_coverage` |

## 💎 Source files

- `agent/heat_planner/tools/prediction.py`
- Root `README.md` — "And one required differentiator: BigQuery ML"
