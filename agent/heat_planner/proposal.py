"""Drafts the council or dispatch memo for a track from the figures the analysis produced, and nothing else."""

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from .config import load_settings

logger = logging.getLogger(__name__)

AUDIENCE = {"today": "the city's emergency management dispatcher, for this afternoon",
            "budget": "a city council meeting deciding where to fund permanent cooling centers",
            "trees": "the sustainability and urban forestry office, for a multi-year planting program"}

PROMPT = """You are drafting a short memo for {audience}.

Use ONLY the figures in the JSON below. Do not add any number, name, cost or fact that is not in it. Where the JSON says something is
not available (cost, land use, canopy, pavement), say so plainly and say what would be needed.

Write 250 to 350 words in plain text with these short headings: Recommendation, Why these areas, Who it reaches, How often it matters
(only if the figures include heat days), Limits and what we still need, Next steps. Refer to places by their area names. Write every share or fraction as a percentage (0.295 means 29.5%), and leave out internal score values. Do not use race or ethnicity.

FIGURES:
{figures}
"""


def make_client() -> genai.Client:
    s = load_settings()
    return genai.Client(vertexai=True, project=s.project_id or None, location="global")


def draft(track: str, result: dict[str, Any], client: Any = None) -> dict[str, Any]:
    s = load_settings()
    config = types.GenerateContentConfig(temperature=0.2)
    if s.thinking_level and s.llm_model.startswith("gemini-4"):
        config = types.GenerateContentConfig(temperature=0.2, thinking_config=types.ThinkingConfig(thinking_level=s.thinking_level))
    keep = {k: v for k, v in result.items() if k not in {"status"}}
    prompt = PROMPT.format(audience=AUDIENCE.get(track, "a city planner"), figures=json.dumps(keep, default=str)[:12000])
    genai_client = client or make_client()  # keep a reference: a temporary client is closed when it is garbage-collected
    response = genai_client.models.generate_content(model=s.llm_model, contents=prompt, config=config)
    return {"text": (response.text or "").strip(), "track": track}
