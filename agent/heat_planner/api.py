"""FastAPI app: a small JSON API plus the static single-page UI."""

import asyncio
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, forecast, live, mapdata, service
from .bq import ToolError
from .config import load_settings
from .tools.history import heat_frequency
from .tools.prediction import rank_response_sites

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
    return {"ok": True, "city": s.city, "dataset": s.dataset, "bqml_model": s.model_name, "llm_model": s.llm_model,
            "router_model": s.router_model, "live_model": s.live_model}


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


async def _data(fn, *args):
    """Run a blocking data loader off the event loop; show data problems as a clear 503."""
    try:
        return await asyncio.to_thread(fn, *args)
    except ToolError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/map/config")
async def map_config():
    return mapdata.maps_config()


@app.get("/api/map/points")
async def map_points(limit: int = Query(mapdata.MAX_POINTS, ge=1, le=mapdata.MAX_POINTS)):
    return await _data(mapdata.measured_points, limit)


@app.get("/api/map/tracts")
async def map_tracts():
    return {"tracts": await _data(mapdata.tract_predictions)}


@app.get("/api/graph")
async def graph(limit: int = Query(mapdata.GRAPH_DEFAULT_TRACTS, ge=1, le=mapdata.GRAPH_MAX_TRACTS)):
    return await _data(mapdata.graph, limit)


@app.get("/api/forecast")
async def forecast_api():
    return await _data(forecast.get_forecast)


@app.get("/api/history")
async def history_api(threshold: float = Query(100.0, ge=80, le=130)):
    result = await asyncio.to_thread(heat_frequency, threshold)
    if result.get("status") != "ok":
        raise HTTPException(status_code=503, detail=result.get("message", "history unavailable"))
    return result


@app.get("/api/priority")
async def priority_api(limit: int = Query(8, ge=1, le=25)):
    result = await asyncio.to_thread(rank_response_sites, limit)
    if result.get("status") != "ok":
        raise HTTPException(status_code=503, detail=result.get("message", "ranking unavailable"))
    return result


@app.websocket("/api/live")
async def live_socket(ws: WebSocket):
    if not live.same_origin(ws.headers):
        await ws.close(code=1008)
        return
    await ws.accept()
    await live.run_session(ws)
    try:
        await ws.close()
    except RuntimeError:  # already closed by the browser
        pass


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
