"""Specialist sub-agents. Each owns a small set of tools so routing stays unambiguous."""

from typing import Any

from google.adk.agents import Agent

from . import callbacks, prompts
from .config import load_settings
from .context import AgentContext
from .tools import (
    community_profile,
    dispatch_today_fleet,
    heat_frequency,
    plan_tree_canopy,
    predict_heat_offset,
    rank_response_sites,
    recommend_cooling_centers,
)


def _instruction(text: str):
    # A provider, so braces in the text are never read as session-state variables.
    return lambda _readonly_context: text


def build_sub_agents(ctx: AgentContext, model: Any = None) -> list[Agent]:
    model = model or load_settings().llm_model
    shared = callbacks.wire(ctx)
    return [
        Agent(
            name="prediction_analyst",
            model=model,
            description="Predicts how much hotter or cooler a location is than average, explains why, "
            "and runs all three decision tracks: Track 1 (Today: up to 20 hydration trucks + fire engines "
            "and 10 mobile wellness checks), Track 2 (Budget Cycle: up to 3 permanent cooling centers + "
            "nearest library), and Track 3 (Decade: 10-year tree canopy planting plan).",
            instruction=_instruction(prompts.PREDICTION),
            tools=[
                predict_heat_offset,
                rank_response_sites,
                dispatch_today_fleet,
                recommend_cooling_centers,
                plan_tree_canopy,
            ],
            **shared,
        ),
        Agent(
            name="history_analyst",
            model=model,
            description="Reports how often the city reaches a temperature and whether that is rising, "
            "from seven years of weather-station history.",
            instruction=_instruction(prompts.HISTORY),
            tools=[heat_frequency],
            **shared,
        ),
        Agent(
            name="community_analyst",
            model=model,
            description="Describes who lives around a location: population, age, poverty, "
            "households without a car.",
            instruction=_instruction(prompts.COMMUNITY),
            tools=[community_profile],
            **shared,
        ),
    ]
