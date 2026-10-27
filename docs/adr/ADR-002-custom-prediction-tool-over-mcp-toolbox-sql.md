# ADR-002 — Custom Python tool vs. MCP Toolbox SQL-only tool for the prediction wrapper

| **Status** | Done |
| --- | --- |
| **Owner** | @deviranjani |
| **Contributors** | @deviranjani |
| **Approved** | @deviranjani |
| **Due date** | 2026-Q4 (hackathon submission) |
| **Decision** | Implement `predict_heat_offset` and `rank_response_sites` as Python tool functions (`tools/prediction.py`), not as parameterized-SQL tools in MCP Toolbox for Databases |

---

## ❓ Problem statement

---

The challenge requires "at least one tool you built" and names two legitimate shapes for it:
a Python function tool, or a tool defined in MCP Toolbox for Databases as parameterized SQL.
The root README is explicit that running `ML.PREDICT`/`ML.EXPLAIN_PREDICT` through Toolbox
with no Python at all is "a legitimate design" — so the two options are not a correctness
question, they're a design trade-off about where the non-trivial logic should live: turning a
vague location into validated coordinates, deciding when a location is out of coverage,
flattening `ML.EXPLAIN_PREDICT`'s nested attributions into something an agent can say in
plain language, and blending three signals into a single ranked list.

## 💡 Research insights

---

- The root README's own guidance: "What we're actually looking for is the work that *isn't*
  a single query... That tends to want Python. But if you can express it in Toolbox and
  defend the choice, that counts."
- `rank_response_sites`'s `score_sites()` blends three z-scored signals (heat offset,
  no-vehicle rate, median age) with configurable weights — this is non-trivial numeric logic
  (z-scoring, weighted sum, sort) that would need to live in SQL `WINDOW`/`STDDEV` functions
  if pushed into Toolbox, with materially worse readability and testability than a pure
  Python function (`score_sites` is directly unit-tested with plain dicts, no BigQuery
  involved — see `test_tools.py::test_score_sites_ranks_hot_and_vulnerable_first`).
- Coverage-box checking (`_within_coverage`) and attribution flattening (`_attributions`) are
  both reused across two tools and the map/graph data endpoints (`mapdata.py`) — a shared
  Python module is the natural place for logic used by three different call sites.

## 📊 Solution hypothesis

---

- Keeping the "shape the response" logic in Python makes it independently unit-testable
  (`test_tools.py` tests `score_sites`, `_attributions`, coverage validation with zero
  BigQuery involvement) and reusable across `predict_heat_offset`, `rank_response_sites`,
  and the map/graph endpoints in `mapdata.py` — a parameterized-SQL Toolbox tool could not be
  shared this way without duplicating the logic in SQL.

## 🌈 Design options

| | **Option 1 — MCP Toolbox, parameterized SQL only** | **Option 2 ⭐️ CONFIRMED 2026-10-27 — Custom Python tool functions** |
| --- | --- | --- |
| **Overview** | Define `predict_heat_offset`/`rank_response_sites` as Toolbox YAML tools wrapping a parameterized `ML.EXPLAIN_PREDICT` query; ranking logic expressed in SQL window functions. | Python functions in `tools/prediction.py`, calling `bq.run_query()` directly, with `_within_coverage`, `_attributions`, and `score_sites` as plain Python helpers. |
| **HLD** | ```mermaid\ngraph LR\n  A[ADK Agent] --> B[MCP Toolbox]\n  B --> C[ML.EXPLAIN_PREDICT SQL]\n```| ```mermaid\ngraph LR\n  A[ADK Agent] --> B[predict_heat_offset / rank_response_sites]\n  B --> C[bq.run_query]\n  B --> D[mapdata.py reuses same helpers]\n```|
| **Link** | root `README.md` — "What 'a tool you built' means" | `agent/heat_planner/tools/prediction.py` |
| **Benefits and risks** | ➕ No Python tool-wiring code<br>➕ Still satisfies the challenge's "a tool you built" requirement if the SQL is genuinely authored, not generic<br>➖ Ranking's z-score blend is awkward and less readable in SQL window functions<br>➖ Coverage-box check and attribution flattening would need to be duplicated in both the Toolbox tool and `mapdata.py`'s Python code (no shared module) | ➕ Z-score ranking, coverage check, and attribution flattening are each unit-tested in isolation with no BigQuery dependency<br>➕ Shared with `mapdata.py`'s map/graph endpoints — one definition of "what the model says"<br>➕ Easier to add the `safe_tool` exception-safety wrapper uniformly<br>➖ More Python wiring code than a pure-SQL tool |
| **Tasks** | — (rejected) | Implemented: `tools/prediction.py`, `tools/_common.py`, reused by `mapdata.py` |

## ✅ Follow up

| **Decision** | **Status** | **Next steps** |
| --- | --- | --- |
| Python tool functions for prediction/ranking; MCP Toolbox or BigQuery's built-in MCP server may still be the right choice for simpler "query my tables" access elsewhere in the agent | decided | If a future tool is a pure query with no shaping logic, prefer a managed MCP server over writing another Python tool, per the root README's own guidance |

## 💎 Source files

- `agent/heat_planner/tools/prediction.py`
- `agent/heat_planner/tools/_common.py`
- `agent/heat_planner/mapdata.py`
- Root `README.md` — "Choosing your MCP server", "What 'a tool you built' means"
