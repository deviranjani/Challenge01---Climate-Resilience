"""Root agent. `build_root_agent` makes one per request; `root_agent` serves `adk web` and `adk run`."""

import logging
from typing import Any

from google.adk.agents import Agent

from . import callbacks, prompts
from .config import load_settings
from .context import AgentContext
from .sub_agents import build_sub_agents, thinking_planner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def build_root_agent(ctx: AgentContext, model: Any = None, track: str | None = None) -> Agent:
    settings = load_settings()
    router = model or settings.router_model  # an explicit model (tests) is used everywhere
    return Agent(
        name="heat_planner",
        model=router,
        description="Heat-response planning assistant for three tracks (emergency response, cooling centers, tree planting) "
        "that routes questions to specialists.",
        instruction=lambda _readonly_context: prompts.root(settings.city, track),
        sub_agents=build_sub_agents(ctx, model),
        planner=thinking_planner(router),
        **callbacks.wire(ctx),
    )


root_agent = build_root_agent(AgentContext())
