"""Runtime configuration, read from the environment so the same code runs locally and on Cloud Run."""

import os
from dataclasses import dataclass

# Gemini on Vertex AI, authenticated by the runtime service account (no API key to manage).
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.environ.get("HEAT_VERTEX_LOCATION", "us-central1"))

AGENT_MAX_STEPS = int(os.environ.get("HEAT_AGENT_MAX_STEPS", "12"))
AGENT_HISTORY_TURNS = 12
MAX_QUESTION_CHARS = 1000

# Operational guardrails across the three climate-resilience tracks (City of Dallas defaults).
MAX_HYDRATION_TRUCKS = int(os.environ.get("HEAT_MAX_HYDRATION_TRUCKS", "20"))
MAX_WELLNESS_UNITS = int(os.environ.get("HEAT_MAX_WELLNESS_UNITS", "10"))
MAX_COOLING_CENTERS = int(os.environ.get("HEAT_MAX_COOLING_CENTERS", "3"))
MAX_CANOPY_ZONES = int(os.environ.get("HEAT_MAX_CANOPY_ZONES", "10"))


@dataclass(frozen=True)
class Settings:
    project_id: str
    dataset: str
    model_name: str
    llm_model: str
    city: str
    location: str
    max_bytes_billed: int
    max_rows: int


def load_settings() -> Settings:
    return Settings(
        project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        dataset=os.environ.get("BQ_DATASET", "a4i_climate"),
        model_name=os.environ.get("BQML_MODEL", "offset_model"),
        llm_model=os.environ.get("HEAT_AGENT_MODEL", "gemini-2.5-flash"),
        city=os.environ.get("HEAT_CITY", "Dallas"),
        location=os.environ.get("BQ_LOCATION", "US"),
        # Hard ceiling per query so a bad prompt cannot run up a bill (1 GB).
        max_bytes_billed=int(os.environ.get("BQ_MAX_BYTES_BILLED", str(10**9))),
        max_rows=int(os.environ.get("BQ_MAX_ROWS", "500")),
    )
