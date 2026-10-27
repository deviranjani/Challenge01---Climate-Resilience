"""Runtime configuration, read from the environment so the same code runs locally and on Cloud Run."""

import os
from dataclasses import dataclass

# Gemini on Vertex AI, authenticated by the runtime service account (no API key to manage).
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
# gemini-4-argon is served from the global endpoint; Live models are regional (see live_location).
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.environ.get("HEAT_VERTEX_LOCATION", "global"))

AGENT_MAX_STEPS = int(os.environ.get("HEAT_AGENT_MAX_STEPS", "12"))
AGENT_HISTORY_TURNS = 12
MAX_QUESTION_CHARS = 1000


@dataclass(frozen=True)
class Settings:
    project_id: str
    dataset: str
    model_name: str
    bqml_type: str
    llm_model: str
    router_model: str
    proposal_model: str
    live_model: str
    nws_user_agent: str
    thinking_level: str
    live_location: str
    city: str
    location: str
    max_bytes_billed: int
    max_rows: int


def load_settings() -> Settings:
    return Settings(
        project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        dataset=os.environ.get("BQ_DATASET", "a4i_climate"),
        model_name=os.environ.get("BQML_MODEL", "offset_model"),
        bqml_type=os.environ.get("BQML_MODEL_TYPE", "Linear regression (BigQuery ML LINEAR_REG)"),
        # Chat answers use a fast model: gemini-4-argon took a median of 9-23 s per call and sometimes over 60 s.
        llm_model=os.environ.get("HEAT_AGENT_MODEL", "gemini-3.8-flash"),
        # Drafting a proposal is a one-off writing task where a longer wait is fine, so it keeps the stronger model.
        proposal_model=os.environ.get("HEAT_PROPOSAL_MODEL", "gemini-4-argon"),
        router_model=os.environ.get("HEAT_ROUTER_MODEL", "gemini-3.8-flash"),
        # gemini-4-argon thinks for over a minute by default; LOW answers in a few seconds. Empty turns it off.
        thinking_level=os.environ.get("HEAT_THINKING_LEVEL", "LOW"),
        live_model=os.environ.get("HEAT_LIVE_MODEL", "gemini-live-2.5-flash-native-audio"),
        live_location=os.environ.get("HEAT_LIVE_LOCATION", "us-central1"),
        # api.weather.gov asks every client to identify itself.
        nws_user_agent=os.environ.get("NWS_USER_AGENT", "HeatPlanner/1.0 (hackathon demo)"),
        city=os.environ.get("HEAT_CITY", "Dallas"),
        location=os.environ.get("BQ_LOCATION", "US"),
        # Hard ceiling per query so a bad prompt cannot run up a bill (1 GB).
        max_bytes_billed=int(os.environ.get("BQ_MAX_BYTES_BILLED", str(10**9))),
        max_rows=int(os.environ.get("BQ_MAX_ROWS", "500")),
    )
