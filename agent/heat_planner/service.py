"""Answering one chat message with the Google ADK agent tree.

Each question gets a fresh agent tree and a throw-away in-memory session seeded with the conversation so far. The
browser sends the history, so the server keeps no state. The model never writes SQL: it can only call the tools.
"""

import asyncio
import logging
import re
import uuid
from typing import Any, Optional

from google.adk.agents import RunConfig
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from . import config
from .agent import build_root_agent
from .context import AgentContext

logger = logging.getLogger(__name__)

APP_NAME = "heat_planner"
USER_ID = "planner"
NO_ANSWER = "I could not form an answer from the data I gathered. Try rephrasing the question."
_FOLLOW_RX = re.compile(r"(?is)\n?\s*\**follow-?\s?ups?\**\s*:\**\s*(.+?)\s*$")


class AgentError(Exception):
    """The language model could not be used (not configured, not reachable, or it failed)."""


def split_followups(text: str) -> tuple[str, list[str]]:
    """(answer without the FOLLOW-UPS line, the follow-up questions)."""
    match = _FOLLOW_RX.search(text or "")
    if not match:
        return (text or "").strip(), []
    questions = [re.sub(r"^[\s\-\*\d\.\)]+", "", q).strip(" *") for q in re.split(r"\||\n", match.group(1))]
    return text[: match.start()].strip(), [q for q in questions if 4 < len(q) <= 160][:4]


def clean_history(history: Optional[list[dict[str, Any]]]) -> list[dict[str, str]]:
    """The last turns as {role, text}, starting with a user turn (models want alternating roles)."""
    turns = [
        {"role": "user" if m.get("role") == "user" else "assistant", "text": str(m.get("text", ""))[:4000]}
        for m in (history or [])[-config.AGENT_HISTORY_TURNS:]
        if str(m.get("text", "")).strip()
    ]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


def _final_text(event: Event) -> Optional[str]:
    if not event.is_final_response() or not event.content or not event.content.parts:
        return None
    return "".join(p.text for p in event.content.parts if getattr(p, "text", None) and not getattr(p, "thought", False))


async def _converse(agent: Any, history: list[dict[str, str]], question: str) -> str:
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=uuid.uuid4().hex)
    for turn in history:
        author, role = ("user", "user") if turn["role"] == "user" else (agent.name, "model")
        await sessions.append_event(
            session, Event(author=author, content=types.Content(role=role, parts=[types.Part.from_text(text=turn["text"])]))
        )
    runner = Runner(app_name=APP_NAME, agent=agent, session_service=sessions)
    final = ""
    try:
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            run_config=RunConfig(max_llm_calls=config.AGENT_MAX_STEPS + 2),
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=question)]),
        ):
            text = _final_text(event)
            if text is not None:
                final = text
    finally:
        await runner.close()
    return final


def run(question: str, history: Optional[list[dict[str, Any]]] = None, model: Any = None) -> dict[str, Any]:
    """Answer one chat message. Synchronous on purpose: the API runs it in a worker thread."""
    question = (question or "").strip()[: config.MAX_QUESTION_CHARS]
    if not question:
        raise AgentError("Ask a question first.")
    ctx = AgentContext()
    try:
        text = asyncio.run(_converse(build_root_agent(ctx, model), clean_history(history), question))
    except Exception as exc:
        logger.exception("agent run failed")
        if "ResourceExhausted" in type(exc).__name__ or "429" in str(exc):
            raise AgentError("The language model is busy right now (rate limited). Wait a few seconds and ask again.") from exc
        raise AgentError(f"The assistant could not answer: {type(exc).__name__}") from exc
    message, followups = split_followups(text or ctx.last_text)
    steps = [{k: v for k, v in s.items() if k != "started"} for s in ctx.steps]
    return {"message": message or NO_ANSWER, "cards": ctx.cards, "steps": steps, "followups": followups,
            "stopped_early": ctx.limit_hit}
