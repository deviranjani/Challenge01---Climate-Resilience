"""Drive the real ADK loop (root agent -> sub-agent -> tool) with a scripted model, so no Vertex AI call is made."""

from typing import AsyncGenerator

import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

from heat_planner import service
from heat_planner.tools import history


class ScriptedLlm(BaseLlm):
    model: str = "scripted"
    script: list = []

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        step = self.script.pop(0)
        if isinstance(step, tuple):
            part = types.Part(function_call=types.FunctionCall(name=step[0], args=step[1]))
        else:
            part = types.Part(text=step)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def scripted(*steps):
    return ScriptedLlm(script=list(steps))


def test_split_followups():
    text, follow = service.split_followups("Answer here.\nFOLLOW-UPS: What about 105F? | Who lives there?")
    assert text == "Answer here."
    assert follow == ["What about 105F?", "Who lives there?"]
    assert service.split_followups("No follow ups")[1] == []


def test_clean_history_starts_with_user_and_caps_length():
    turns = service.clean_history([
        {"role": "assistant", "text": "hello"}, {"role": "user", "text": "q"}, {"role": "assistant", "text": ""},
    ])
    assert turns == [{"role": "user", "text": "q"}]


def test_empty_question_is_rejected():
    with pytest.raises(service.AgentError):
        service.run("   ")


def test_full_loop_routes_to_sub_agent_and_collects_card(monkeypatch):
    rows = [{"year": 2019, "days": 12}, {"year": 2024, "days": 30}]
    monkeypatch.setattr(history, "run_query", lambda *a, **k: rows)
    model = scripted(
        ("transfer_to_agent", {"agent_name": "history_analyst"}),
        ("heat_frequency", {"threshold_f": 100}),
        "Days at 100F rose from 12 to 30.\nFOLLOW-UPS: What about 105F? | Who is most exposed?",
    )
    out = service.run("How often does it hit 100F?", model=model)

    assert out["message"] == "Days at 100F rose from 12 to 30."
    assert out["followups"] == ["What about 105F?", "Who is most exposed?"]
    assert [s["tool"] for s in out["steps"]] == ["heat_frequency"]  # routing is not shown as a step
    assert out["steps"][0]["ms"] >= 0 and "started" not in out["steps"][0]
    card = out["cards"][0]
    assert card["tool"] == "heat_frequency" and card["result"]["days_per_year"][-1]["days"] == 30


def test_tool_error_becomes_an_error_step_not_a_crash(monkeypatch):
    model = scripted(
        ("transfer_to_agent", {"agent_name": "history_analyst"}),
        ("heat_frequency", {"threshold_f": 5}),  # below the allowed range
        "I could not check that threshold.",
    )
    out = service.run("How often is it 5F?", model=model)
    assert out["steps"][0]["error"]
    assert out["cards"][0]["result"]["status"] == "error"


def test_step_budget_stops_a_looping_model(monkeypatch):
    from heat_planner import config

    monkeypatch.setattr(config, "AGENT_MAX_STEPS", 2)
    monkeypatch.setattr(history, "run_query", lambda *a, **k: [])
    loop = [("transfer_to_agent", {"agent_name": "history_analyst"})] + [("heat_frequency", {"threshold_f": 100})] * 20
    out = service.run("loop forever", model=scripted(*loop))
    assert out["stopped_early"] is True
