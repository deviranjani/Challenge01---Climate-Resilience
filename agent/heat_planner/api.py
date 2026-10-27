"""FastAPI app: a small JSON API plus the static single-page UI."""

import asyncio
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, service
from .config import load_settings

logger = logging.getLogger("heat_planner.api")
STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"

app = FastAPI(title="Heat Planner", docs_url="/api/docs", openapi_url="/api/openapi.json")


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=config.MAX_QUESTION_CHARS)
    history: list[Turn] = Field(default_factory=list, max_length=24)


@app.exception_handler(Exception)
async def server_error(_, exc: Exception):
    logger.exception("request failed")
    return JSONResponse(status_code=500, content={"error": f"{type(exc).__name__}"})


@app.get("/api/health")
def health():
    s = load_settings()
    return {"ok": True, "city": s.city, "dataset": s.dataset, "bqml_model": s.model_name, "llm_model": s.llm_model}


@app.get("/api/starters")
def starters():
    city = load_settings().city
    return {"suggestions": [
        f"Where should we send hydration trucks first in {city}?",
        "How often does it reach 100F, and is it getting worse?",
        "How much hotter than average is latitude 32.78, longitude -96.80, and why?",
        "Who lives within 2 km of latitude 32.78, longitude -96.80?",
    ]}


@app.post("/api/chat")
async def chat(body: ChatIn):
    try:
        return await asyncio.to_thread(
            service.run, body.question, [t.model_dump() for t in body.history]
        )
    except service.AgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
