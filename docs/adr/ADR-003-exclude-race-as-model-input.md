# ADR-003 — Exclude race/ethnicity as a model input; audit it only post-hoc on output

| **Status** | Done |
| --- | --- |
| **Owner** | @deviranjani |
| **Contributors** | @deviranjani |
| **Approved** | @deviranjani |
| **Due date** | 2026-Q4 (hackathon submission) |
| **Decision** | Never use race/ethnicity as a model feature or an agent reasoning factor; compare the demographic composition of the agent's recommended sites against the city as a whole, after the fact, as an equity audit |

---

## ❓ Problem statement

---

Vulnerability indices commonly used for heat-response planning (NYC's Heat Vulnerability
Index, CDC's Social Vulnerability Index) include race as a direct input variable, because
race correlates with urban heat exposure — formerly redlined neighborhoods measurably run
hotter today. The challenge's own data deliberately omits those indices and their race
columns. Without an explicit decision here, a well-intentioned feature addition (e.g. "add a
demographic vulnerability score") could reintroduce race as a model input through a secondary
dataset, or a prompt could instruct the agent to reason about race directly — both of which
the root README identifies as the wrong fix ("removing the column does not make your model
unbiased... every proxy is still there").

## 💡 Research insights

---

- Root `README.md`: "The *cause* is the physical environment: pavement, building density,
  missing tree cover. Those we can measure directly, and they're in your data. Race is a
  cruder measurement of something we already have."
- Root `README.md`: "Strip the variable. Audit the outcome. Say you did both." — this is
  explicitly a two-part policy, not deletion alone.
- `tools/community.py:58` already encodes the audit-not-input distinction in its own output:
  `"note": "Population-weighted averages of tract values. Race and ethnicity are not used by
  design."`
- `prompts.py:24` (`ROOT`) and `prompts.py:47` (`COMMUNITY`) both instruct the agent never to
  use race/ethnicity to justify a recommendation or discuss it — this ADR formalizes a
  decision the prompts already implement, so future prompt or feature changes have something
  explicit to check against rather than re-deriving the reasoning from scratch.

## 📊 Solution hypothesis

---

- Training the model on `poverty_rate`, `no_vehicle_rate`, `median_age`, and physical/
  environmental features (not race) will still surface real vulnerability if that
  vulnerability is physically grounded — testable via the equity audit (compare recommended
  tracts' demographics against the city average, per the root README's 3-step process).
- If recommended sites skew toward high-poverty, low-vehicle-access, older-resident tracts,
  that is evidence the model finds real vulnerability through its legitimate features. If they
  skew the other way, that is itself a finding worth reporting, not a result to hide.

## 🌈 Design options

| | **Option 1 — Include a vulnerability index with race as an input** | **Option 2 — Omit race, do nothing further** | **Option 3 ⭐️ CONFIRMED 2026-10-27 — Omit race as input, audit output demographics explicitly** |
| --- | --- | --- | --- |
| **Overview** | Join an external vulnerability index (e.g. CDC SVI) that includes race directly into the model's features. | Simply don't add a race column; no further check. | Don't add a race column; separately compute and report the demographic composition (poverty, no-vehicle, age, and race for comparison only) of the model's top recommendations vs. the city average. |
| **HLD** | ```mermaid\ngraph LR\n  A[External SVI] --> B[offset_model features]\n  B --> C[prediction]\n```| ```mermaid\ngraph LR\n  A[tract_demographics minus race] --> B[offset_model features]\n  B --> C[prediction]\n```| ```mermaid\ngraph LR\n  A[tract_demographics minus race] --> B[offset_model features]\n  B --> C[rank_response_sites]\n  C --> D[equity audit: compare recommended tracts vs city average]\n```|
| **Link** | root `README.md` — "One thing we deliberately excluded" | root `README.md` — same section | root `README.md` — "What 'auditing the outcome' actually means" |
| **Benefits and risks** | ➕ May correlate strongly with exposure<br>➖ Race as a direct model input is explicitly the thing this challenge's data was designed to avoid<br>➖ "Removing the column does not make your model unbiased" cuts the other way too — *adding* it doesn't make the model more honest, it makes bias explicit and harder to justify | ➕ Simple, matches the provided data as-is<br>➖ No way to know whether the model's recommendations are actually reaching vulnerable neighborhoods or just the easiest-to-model ones — "a slide claiming everything worked" with no evidence | ➕ Matches the challenge's explicit two-part policy<br>➕ Produces a genuine, defensible finding either way (model finds real vulnerability, or model needs better features) — exactly what judges reward under "Rigor and judgment" (25% of score)<br>➖ Requires building the audit step (tract lookup + comparison), not just the prediction |
| **Tasks** | — (rejected) | — (rejected — insufficient on its own per root README) | Prompts already enforce "never use race to justify a recommendation" (`prompts.py`); `tools/community.py` already notes race is excluded by design; **the full three-step equity audit comparing recommended-site demographics to the city average is not yet built as a dedicated tool/output** — tracked in `docs/modernization/runs/2026-10-27/bootstrap-findings.md` as an open item, not fabricated as done here |

## ✅ Follow up

| **Decision** | **Status** | **Next steps** |
| --- | --- | --- |
| Never add race/ethnicity as a model feature or agent reasoning input | decided | Enforced in `.claude/rules/adk-agent.md`'s prompt-review guidance and `.claude/skills/review-checklist/SKILL.md` |
| Build the explicit equity-audit comparison (recommended tracts vs. city-average demographics) as a first-class output, not just a documented intention | in review | Not implemented as of this bootstrap run (2026-10-27) — recorded as an open gap in `docs/modernization/runs/2026-10-27/bootstrap-findings.md`; this ADR does not claim it exists |

## 💎 Source files

- `agent/heat_planner/prompts.py`
- `agent/heat_planner/tools/community.py`
- Root `README.md` — "The data, and why we chose it", "What 'auditing the outcome' actually means"
