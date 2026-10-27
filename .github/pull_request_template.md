## What changed

<!-- One or two sentences. Which lane: data / agent / frontend / story? -->

## Why

<!-- What question or gap does this address? Link the planner question from the root README if relevant. -->

## Checklist

- [ ] `cd agent && .venv/bin/python -m pytest` passes (if `agent/` changed)
- [ ] New tools are wrapped in `@safe_tool` and validate their inputs (see `.claude/rules/bigquery.md`)
- [ ] No hardcoded secret, API key, or project ID (see `.claude/skills/security/SKILL.md`)
- [ ] No new feature or prompt change reintroduces race/ethnicity as a model input or reasoning factor (see `docs/adr/ADR-003-exclude-race-as-model-input.md`)
- [ ] Governance files (`CLAUDE.md`, `.claude/rules/*.md`) updated if this PR introduces a pattern they don't yet cover, or `No governance updates needed`

## Notes for reviewers

<!-- Anything a reviewer should know before using .claude/skills/review-checklist/SKILL.md -->
