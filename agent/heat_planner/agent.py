"""Root agent. `build_root_agent` makes one per request; `root_agent` serves `adk web` and `adk run`."""

import logging
from typing import Any

from google.adk.agents import Agent

from . import callbacks, prompts
from .config import load_settings
from .context import AgentContext
from .sub_agents import build_sub_agents

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def build_root_agent(ctx: AgentContext, model: Any = None) -> Agent:
    settings = load_settings()
    model = model or settings.llm_model
    return Agent(
        name="heat_planner",
        model=model,
        description="Heat-response planning assistant that routes questions to prediction, "
        "history and community specialists.",
        instruction=lambda _readonly_context: prompts.ROOT.format(city=settings.city),
        sub_agents=build_sub_agents(ctx, model),
        **callbacks.wire(ctx),
    )


root_agent = build_root_agent(AgentContext())
