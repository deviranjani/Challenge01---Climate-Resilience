---
name: adk-agent-design
description: 'How to add or change a sub-agent, tool, or prompt rule in the heat_planner ADK agent tree without breaking routing. Use when: adding a new specialist sub-agent, adding a tool to an existing sub-agent, or changing a system prompt. Trigger phrases: "add a new sub-agent", "add a tool to the agent", "change the agent prompt", "the agent routed to the wrong specialist".'
---

# ADK Agent Design

## When to Use This Skill

When adding a new sub-agent, adding a tool to an existing sub-agent, or changing prompt
text in `agent/heat_planner/prompts.py`.

## Prerequisites

Read `.claude/rules/adk-agent.md` for the rules; this skill walks through the how-to.

## Adding a Tool to an Existing Sub-Agent

1. Write the tool function in the right file under `agent/heat_planner/tools/` (or a new file
   if it's a new domain), following the pattern in `tools/prediction.py`/`tools/history.py`:
   a clear docstring (ADK uses it for routing), `@safe_tool`, input validation via
   `tools/_common.py`.
2. Register it in the sub-agent's `tools=[...]` list in `sub_agents.py`.
3. Update that sub-agent's prompt in `prompts.py` if the new tool changes what questions it
   should handle.
4. Add a `test_tools.py`-style unit test and verify `test_agent_wiring.py`'s assertions about
   each sub-agent's tool set still pass (update them if the set intentionally changed).

## Adding a New Sub-Agent

1. Add a new prompt constant in `prompts.py`, following the existing style: state what the
   agent answers, which tool(s) it uses, what caveats to always include, and what NOT to do
   (e.g. "Never discuss race or ethnicity" in `COMMUNITY`).
2. Add the `Agent(...)` construction in `sub_agents.py:build_sub_agents`, with its own small
   tool set and `**callbacks.wire(ctx)` for shared callback wiring — don't invent a second
   callback-wiring path.
3. Update `prompts.py`'s `ROOT` instruction to describe when to route to the new specialist.
4. Add it to `test_agent_wiring.py`'s `test_root_agent_routes_to_three_specialists`-style
   assertion (rename/generalize the test if the specialist count changes).
5. Consider a `ScriptedLlm`-based test in `test_service.py`'s style that exercises routing to
   the new sub-agent end to end.

## Changing a Prompt

Prompt text in `prompts.py` is a safety mechanism, not just a style choice — it encodes:
refusal conditions (other cities, invented coordinates), required caveats (one afternoon's
pattern, extrapolation away from measured roads), and the `FOLLOW-UPS:` output contract that
`service.py:split_followups()` parses with a regex. If you change the `FOLLOW-UPS:` format,
update the regex (`service.py:28`, `_FOLLOW_RX`) in the same change, and update
`test_service.py::test_split_followups`.

## Checklist

- [ ] New tool has a docstring ADK can route on, `@safe_tool`, and input validation
- [ ] Sub-agent tool sets remain small and non-overlapping
- [ ] Root prompt's routing guidance updated if a new sub-agent or tool changes what it should handle
- [ ] `FOLLOW-UPS:` format changes keep `service.py`'s parser regex in sync
- [ ] `test_agent_wiring.py` and/or a `test_service.py` scripted test cover the change

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
