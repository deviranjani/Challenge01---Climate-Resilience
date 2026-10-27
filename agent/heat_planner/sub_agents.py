"""Specialist sub-agents. Each owns a small set of tools so routing stays unambiguous."""

from typing import Any

from google.adk.agents import Agent

from . import callbacks, prompts
from .config import load_settings
from .context import AgentContext
from .tools import community_profile, heat_frequency, predict_heat_offset, rank_response_sites


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
            "and ranks where heat relief should go first. Uses the BigQuery ML model.",
            instruction=_instruction(prompts.PREDICTION),
            tools=[predict_heat_offset, rank_response_sites],
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
