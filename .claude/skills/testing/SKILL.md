---
name: testing
description: 'How to write and run tests for the heat_planner agent — mocking BigQuery with fake_runner, driving the real ADK loop with a ScriptedLlm, and FastAPI TestClient usage. Use when: adding a new tool, changing agent routing, or writing a test for agent/heat_planner/. Trigger phrases: "write a test for this", "how do I mock BigQuery here", "test this tool", "test the agent".'
---

# Testing

## When to Use This Skill

When adding a new tool, sub-agent, or API route to `agent/heat_planner/` and you need to
write a test that doesn't call live BigQuery or Vertex AI.

## Prerequisites

Read `.claude/rules/testing.md` for the rules; this skill is the how-to walkthrough.

## Mocking a BigQuery-backed Tool

```python
# test_tools.py pattern
def fake_runner(*responses):
    """Return a run_query stand-in that yields each response in turn and records the SQL."""
    calls = []
    queue = list(responses)
    def run(sql, params=(), settings=None, max_rows=None):
        calls.append((sql, list(params)))
        return queue.pop(0)
    run.calls = calls
    return run

def test_my_new_tool(monkeypatch):
    monkeypatch.setattr(my_module, "run_query", fake_runner([{"col": "value"}]))
    result = my_module.my_new_tool(42)
    assert result["status"] == "ok"
```

A tool that issues more than one query (like `predict_heat_offset`: coverage query, then
`ML.EXPLAIN_PREDICT`) needs one response per call, in order — `fake_runner` pops them in
call order.

## Driving the Real Agent Loop (no live Gemini call)

```python
# test_service.py pattern — a ScriptedLlm yields pre-scripted steps
class ScriptedLlm(BaseLlm):
    model: str = "scripted"
    script: list = []
    async def generate_content_async(self, llm_request, stream=False):
        step = self.script.pop(0)
        if isinstance(step, tuple):
            part = types.Part(function_call=types.FunctionCall(name=step[0], args=step[1]))
        else:
            part = types.Part(text=step)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))

model = ScriptedLlm(script=[
    ("transfer_to_agent", {"agent_name": "history_analyst"}),
    ("heat_frequency", {"threshold_f": 100}),
    "Days at 100F rose from 12 to 30.\nFOLLOW-UPS: ...",
])
out = service.run("How often does it hit 100F?", model=model)
```

This exercises real ADK routing (`transfer_to_agent`), real callback wiring (step count,
tool trace, error handling), and real `split_followups()` parsing — only the Gemini network
call is replaced.

## Testing a New FastAPI Route

```python
# test_api.py pattern
def test_new_route(client, monkeypatch):
    monkeypatch.setattr(my_module, "the_thing_it_calls", lambda *a: {"ok": True})
    res = client.get("/api/new-route")
    assert res.status_code == 200
```

Use the existing `client` fixture (`TestClient(api.app)`); monkeypatch the function the
route calls, not `httpx`/FastAPI internals.

## Checklist

- [ ] No test calls live BigQuery or Vertex AI
- [ ] A multi-query tool's test supplies one `fake_runner` response per query, in call order
- [ ] A routing/callback change has a `ScriptedLlm`-based test, not just a unit test of the tool in isolation
- [ ] `conftest.py`'s autouse fixture (`GOOGLE_CLOUD_PROJECT=test-project`, `prediction._coverage.cache_clear()`) is relied on, not re-implemented per test

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
