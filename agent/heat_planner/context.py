"""State of one chat question: the cards produced by tools and the trace of what was called."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Everything the callbacks of one question share. Created per request, never reused."""

    cards: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    model_calls: int = 0
    model_started: float = 0.0
    last_text: str = ""
    limit_hit: bool = False
