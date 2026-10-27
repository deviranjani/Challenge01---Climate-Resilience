# Architecture Decision Records

ADRs for `Challenge01---Climate-Resilience`, following the Search & Recommendations
Principals ADR format (metadata table + 7 sections). Author new ADRs from the canonical
template in `.claude/skills/bootstrap-governance/templates/adr.template.md` when present —
do not commit a template copy into this repo.

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-bigquery-ml-explain-predict-for-heat-offset.md) | BigQuery ML + `ML.EXPLAIN_PREDICT` for the heat-offset prediction | Done |
| [ADR-002](ADR-002-custom-prediction-tool-over-mcp-toolbox-sql.md) | Custom Python tool vs. MCP Toolbox SQL-only tool for the prediction wrapper | Done |
| [ADR-003](ADR-003-exclude-race-as-model-input.md) | Exclude race/ethnicity as a model input; audit it only post-hoc on output | Done |

## Workflow

1. `ls docs/adr/ADR-*.md | sort` — find the next number
2. `docs/adr/ADR-NNN-short-kebab-title.md` (3-digit zero-padded)
3. Update this index table
4. If superseding an existing ADR, update its Status to `Superseded by ADR-NNN (YYYY-MM-DD)`
