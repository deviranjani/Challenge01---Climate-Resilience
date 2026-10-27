"""Drive the real ADK loop (root agent -> sub-agent -> tool) with a scripted model, so no Vertex AI call is made."""

from typing import AsyncGenerator

import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

from heat_planner import service
from heat_planner.tools import history, tracks


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


def test_full_loop_routes_to_prediction_analyst_for_track2_cooling_centers(monkeypatch):
    sample_rows = [
        {
            "geo_id": f"48113000{i}00",
            "latitude": 32.77 + i * 0.01,
            "longitude": -96.79 + i * 0.01,
            "predicted_offset_f": 2.5 + i * 0.5,
            "no_vehicle_rate": 0.12 + i * 0.02,
            "poverty_rate": 0.18 + i * 0.03,
            "median_age": 36.0 + i,
            "median_year_structure_built": 1975,
            "total_pop": 4200,
            "top_feature_attributions": [{"feature": "dist_center_km", "attribution": 1.1}],
        }
        for i in range(4)
    ]
    queue = [sample_rows, [{"avg_hot_days": 40.0, "years_observed": 7}]]
    monkeypatch.setattr(tracks, "run_query", lambda *a, **k: queue.pop(0))
    model = scripted(
        ("transfer_to_agent", {"agent_name": "prediction_analyst"}),
        ("recommend_cooling_centers", {"max_centers": 3}),
        "Here are the 3 permanent cooling centers paired with nearest libraries.\nFOLLOW-UPS: Track 1 dispatch? | Track 3 trees?",
    )
    out = service.run("Where should we build the 3 permanent cooling centers?", model=model)
    assert [s["tool"] for s in out["steps"]] == ["recommend_cooling_centers"]
    card = out["cards"][0]
    assert card["tool"] == "recommend_cooling_centers"
    assert len(card["result"]["cooling_centers"]) == 3
    assert card["result"]["cooling_centers"][0]["nearest_library"]["name"]


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
