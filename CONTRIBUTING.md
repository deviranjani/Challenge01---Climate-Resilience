# Contributing

This is a hackathon team repo (Agents for Impact 2026, Challenge 1). Lightweight process by
design — the goal is to ship a working demo before the judging deadline, not to slow the team
down with ceremony.

## Branching

Per the root `README.md`'s "One repo, one branch per lane" convention:

```bash
git checkout -b data        # or agent, frontend, story
```

Merge into `main` when another lane needs what you built — don't wait for a single "done"
merge at the end.

## Commits

No strict convention enforced. Prefer a short, plain-language summary of what changed and why
over a formatted commit-type prefix — speed matters more than format here.

## Pull Requests

- Use the template in `.github/pull_request_template.md`.
- Run `cd agent && .venv/bin/python -m pytest` before opening a PR that touches `agent/`.
- See `.claude/skills/review-checklist/SKILL.md` for what a reviewer should check.
- `.github/workflows/secret-scan.yml` and `.github/workflows/governance-gate.yml` run
  automatically and are non-blocking — they report, they don't gate merges, by design (see
  `.github/workflows/governance-gate.yml`'s own comment).

## Code Style

Follow the existing patterns in `agent/heat_planner/` — see `docs/patterns.md` and
`CLAUDE.md`'s Instruction Map. No linter/formatter is currently configured in this repo; match
the surrounding code's style rather than introducing a new one mid-hackathon.

## Questions

See the root `README.md`'s "Getting help" section — table captain first, then the facilitator
and event Discord.
