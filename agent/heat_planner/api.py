"""FastAPI app: a small JSON API plus the static single-page UI."""

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import areas, config, forecast, live, mapdata, proposal, service, tracks, tracts
from .bq import ToolError
from .config import load_settings
from .tools.history import heat_frequency

logger = logging.getLogger("heat_planner.api")
STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"

app = FastAPI(title="Heat Planner", docs_url=None, redoc_url=None, openapi_url=None)  # no public API documentation


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class ChatIn(BaseModel):
    track: Literal["today", "budget", "trees"] | None = None
    question: str = Field(min_length=1, max_length=config.MAX_QUESTION_CHARS)
    history: list[Turn] = Field(default_factory=list, max_length=24)


@app.exception_handler(Exception)
async def server_error(_, exc: Exception):
    logger.exception("request failed")
    return JSONResponse(status_code=500, content={"error": f"{type(exc).__name__}"})


@app.get("/api/health")
def health():
    # A customer-facing app says only whether it is up; model and configuration details stay private.
    return {"ok": True}


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
        result = await asyncio.to_thread(
            service.run, body.question, [t.model_dump() for t in body.history], None, body.track
        )
        result.pop("steps", None)  # the tool trace is for logs and engineers, not for customers
        return result
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


@app.get("/api/tracks")
def tracks_api():
    return {"tracks": list(tracks.TRACKS.values()), "focus": {k: v["label"] for k, v in tracks.FOCUS.items()}}


@app.get("/api/today")
async def today_api(focus: Literal["hydration", "wellness", "cooling_hours"] = "hydration", limit: int = Query(10, ge=1, le=25)):
    return await _decision(tracks.today_sites, focus, limit)


@app.get("/api/budget")
async def budget_api(count: int = Query(3, ge=1, le=8), radius_km: float = Query(1.5, ge=0.5, le=5.0), cost_per_center: float | None = Query(None, ge=0, le=1e9)):
    result = await _decision(tracks.cooling_centers, count, radius_km, cost_per_center)
    days = await asyncio.to_thread(heat_frequency, 100.0)
    result["heat_days"] = None if days.get("status") != "ok" else {"threshold_f": 100, "average_days_per_year": days["average_days"], "peak_year": days["peak_year"],
                                                                      "peak_days": days["peak_days"], "trend": days["trend"], "days_per_year": days["days_per_year"]}
    return result


@app.get("/api/trees")
async def trees_api(limit: int = Query(8, ge=1, le=15)):
    return await _decision(tracks.planting_sites, limit)


async def _decision(fn, *args):
    data = await _data(tracts.load_tracts)
    result = await asyncio.to_thread(fn, data, *args)
    if result.get("status") != "ok":
        raise HTTPException(status_code=503, detail=result.get("message", "no result"))
    return result


@app.get("/api/areas")
async def areas_api():
    data = await _data(tracts.load_tracts)
    return {"areas": areas.known_areas(data, 40), "note": "Neighbourhood names are from Google Maps; any ZIP code in the measured area also works."}


class ProposalIn(BaseModel):
    track: Literal["today", "budget", "trees"]
    focus: Literal["hydration", "wellness", "cooling_hours"] = "hydration"
    count: int = Field(3, ge=1, le=8)
    radius_km: float = Field(1.5, ge=0.5, le=5.0)
    cost_per_center: float | None = Field(None, ge=0, le=1e9)
    limit: int = Field(8, ge=1, le=25)


@app.post("/api/proposal")
async def proposal_api(body: ProposalIn):
    data = await _data(tracts.load_tracts)
    if body.track == "today":
        result = await asyncio.to_thread(tracks.today_sites, data, body.focus, body.limit)
    elif body.track == "budget":
        result = await asyncio.to_thread(tracks.cooling_centers, data, body.count, body.radius_km, body.cost_per_center)
        days = await asyncio.to_thread(heat_frequency, 100.0)
        if days.get("status") == "ok":
            result["heat_days"] = {"threshold_f": 100, "average_days_per_year": days["average_days"], "peak_year": days["peak_year"], "peak_days": days["peak_days"], "trend": days["trend"]}
    else:
        result = await asyncio.to_thread(tracks.planting_sites, data, min(body.limit, 15))
    if result.get("status") != "ok":
        raise HTTPException(status_code=503, detail=result.get("message", "no result"))
    try:
        return await asyncio.to_thread(proposal.draft, body.track, result)
    except Exception:
        logger.exception("proposal drafting failed")
        raise HTTPException(status_code=503, detail="The proposal could not be drafted right now. Try again in a moment.")


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


def _asset_version() -> str:
    """A hash of every file in the UI, so a new deploy can never be served with a stale stylesheet or script."""
    digest = hashlib.sha1()
    for path in sorted(STATIC.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(STATIC).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


ASSET_VERSION = _asset_version()


@app.get("/")
def index():
    """The page, with every /static/ URL stamped with the asset version and told never to be reused without checking."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'(/static/[\w./-]+)(["\'])', rf"\1?v={ASSET_VERSION}\2", html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


class RevalidatedStatic(StaticFiles):
    """Static files that browsers must revalidate (cheap 304s). Without this, a browser can keep an old stylesheet beside a new page."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", RevalidatedStatic(directory=STATIC), name="static")
