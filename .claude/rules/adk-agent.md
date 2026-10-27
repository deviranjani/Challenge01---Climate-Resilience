---
description: "Google ADK agent tree design: root agent, sub-agents, callbacks, prompts, per-request context."
paths:
  - "agent/heat_planner/agent.py"
  - "agent/heat_planner/sub_agents.py"
  - "agent/heat_planner/callbacks.py"
  - "agent/heat_planner/context.py"
  - "agent/heat_planner/prompts.py"
  - "agent/heat_planner/service.py"
---

# ADK Agent Instructions

> Scope: the Google ADK agent tree — root agent, sub-agents, callbacks, prompts, and the
> per-request conversation loop in `agent/heat_planner/service.py`.

## Evidence Used

| Evidence | What it showed |
|---|---|
| `agent.py:16` | `build_root_agent(ctx, model)` builds a fresh `Agent` per request; `root_agent` module-level instance only serves `adk web`/`adk run` |
| `sub_agents.py:18` | 3 sub-agents, each with a small, disjoint tool set (`prediction_analyst`: 2 tools, `history_analyst`: 1, `community_analyst`: 1) |
| `callbacks.py:73` | `wire(ctx)` shares 4 callbacks across every Agent in the tree via one `AgentContext` |
| `prompts.py` | Root prompt explicitly instructs: never invent numbers, decline other cities, ask for coordinates rather than guessing, state the offset caveat, never use race/ethnicity to justify a recommendation, end with a `FOLLOW-UPS:` line |
| `service.py:87` | `run()` creates a fresh `AgentContext` and in-memory `InMemorySessionService` per chat message — server is stateless; the browser resends history |
| `callbacks.py:28` | `before_model` enforces `AGENT_MAX_STEPS` (default 12, `config.py`) and returns a synthetic "I stopped..." response rather than looping forever |

## Rules

- ✅ New capability → new tool on the right sub-agent, not new logic inline in a prompt. Keep each sub-agent's tool set small and non-overlapping so ADK's `transfer_to_agent` routing stays unambiguous (`sub_agents.py` comment: "so routing stays unambiguous").
- ✅ Every sub-agent's `instruction` is wrapped via a no-op provider (`sub_agents.py:13` `_instruction`, `agent.py:24` lambda) so literal `{}` in prompt text is never misread as ADK session-state interpolation.
- ✅ Build a fresh `Agent`/`AgentContext` per request (`service.py:92`). Never reuse a module-level `Agent` across requests outside the `adk web`/`adk run` dev path — per-request state (`ctx.steps`, `ctx.cards`, `ctx.model_calls`) would otherwise leak between users.
- ✅ Any new prompt rule that changes model behavior (e.g. a new refusal condition) goes in `prompts.py`, reviewed the same way as code — prompts are the primary safety mechanism here (no vehicle for other cities, no invented coordinates, no race-based reasoning).
- ❌ Don't let a tool's exception reach the model — route through `tools/_common.py`'s `safe_tool` (see `.claude/rules/bigquery.md`), not a bare `try`/`except` in agent code.
- ❌ Don't add agent-tree state that must survive a process restart or be shared across Cloud Run instances — `InMemorySessionService` and `AgentContext` are explicitly throw-away per request (`service.py` module docstring: "Each question gets a fresh agent tree... The server keeps no state").

## Anti-patterns

- ❌ Routing logic duplicated in a prompt AND in Python — ADK's own `transfer_to_agent` tool handles routing; `callbacks.py:18` explicitly excludes it (`INTERNAL_TOOLS`) from the user-visible tool trace because it is framework routing, not a data step.

## References

- `CLAUDE.md` — hub
- `.claude/rules/bigquery.md` — the tool-safety pattern (`safe_tool`) every tool must use
- `.claude/rules/testing.md` — how the agent tree is tested with a `ScriptedLlm`
- `docs/adr/ADR-002-custom-prediction-tool-over-mcp-toolbox-sql.md` — why `predict_heat_offset`/`rank_response_sites` are Python tools, not MCP Toolbox SQL tools

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
