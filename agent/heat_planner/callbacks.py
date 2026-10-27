"""ADK callbacks: enforce the step budget, record the tool trace, and turn tool results into UI cards."""

import logging
import time
from typing import Any, Callable, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

from . import config
from .context import AgentContext

logger = logging.getLogger(__name__)

STOPPED_NOTE = "\n\nI stopped after the maximum number of steps; ask me to continue if you want more detail."
# The framework's own routing tool is not a data step the user needs to see.
INTERNAL_TOOLS = {"transfer_to_agent"}


def _text_of(response: LlmResponse) -> str:
    parts = response.content.parts if response.content and response.content.parts else []
    return "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))


def before_model(ctx: AgentContext) -> Callable:
    def callback(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
        if ctx.model_calls >= config.AGENT_MAX_STEPS:
            ctx.limit_hit = True
            text = (ctx.last_text or "") + STOPPED_NOTE
            return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))
        ctx.model_calls += 1
        return None

    return callback


def after_model(ctx: AgentContext) -> Callable:
    def callback(callback_context: CallbackContext, llm_response: LlmResponse) -> Optional[LlmResponse]:
        ctx.last_text = _text_of(llm_response) or ctx.last_text
        return None

    return callback


def before_tool(ctx: AgentContext) -> Callable:
    def callback(tool: Any, args: dict[str, Any], tool_context: Any) -> Optional[dict]:
        if tool.name not in INTERNAL_TOOLS:
            ctx.steps.append({"tool": tool.name, "args": dict(args), "started": time.monotonic()})
        return None

    return callback


def after_tool(ctx: AgentContext) -> Callable:
    """Record the timing and keep every tool result as a card the UI can draw."""

    def callback(tool: Any, args: dict[str, Any], tool_context: Any, tool_response: Any) -> Optional[dict]:
        if tool.name in INTERNAL_TOOLS:
            return None
        step = next((s for s in reversed(ctx.steps) if s["tool"] == tool.name and "ms" not in s), None)
        if step:
            step["ms"] = round((time.monotonic() - step.pop("started")) * 1000)
        if isinstance(tool_response, dict):
            if tool_response.get("status") == "error" and step:
                step["error"] = tool_response.get("message", "failed")
            ctx.cards.append({"tool": tool.name, "args": dict(args), "result": tool_response})
        return None

    return callback


def wire(ctx: AgentContext) -> dict[str, Callable]:
    """Keyword arguments to pass to every Agent so the whole tree shares one context."""
    return {
        "before_model_callback": before_model(ctx),
        "after_model_callback": after_model(ctx),
        "before_tool_callback": before_tool(ctx),
        "after_tool_callback": after_tool(ctx),
    }
