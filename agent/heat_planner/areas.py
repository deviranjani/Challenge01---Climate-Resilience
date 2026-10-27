"""Area names, so people can ask about "Oak Cliff" or "75215" instead of coordinates.

Structure comes from BigQuery: `tract_areas` maps every census tract to its ZIP code area and city (built by
scripts/build_areas.sh from US Census ZIP boundaries). Names come from Google Maps Platform, live: reverse geocoding
labels each tract with its neighbourhood, and Places text search turns a typed name into map bounds. Google content is
held in memory for an hour and never stored, which is what Google's terms allow. The server authenticates with its own
service account (OAuth), so no extra API key is involved.
"""

import functools
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from math import asin, cos, radians, sin, sqrt
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

from .bq import ToolError, run_query, table
from .config import load_settings

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocode.googleapis.com/v4beta/geocode/location/{lat},{lon}"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
NAME_TTL_S = 3600
TIMEOUT_S = 10
WORKERS = 12
POINT_RADIUS_KM = 1.5            # for a place that is a point (a park, a landmark) rather than an area
BIAS_RADIUS_M = 60000            # prefer matches near the measured area
NEIGHBOURHOOD_TYPES = {"neighborhood", "sublocality", "sublocality_level_1"}
AREA_TYPES = NEIGHBOURHOOD_TYPES | {"locality", "postal_code", "administrative_area_level_3"}
LOOKUP_DOWN = "Google Maps place lookup is unavailable right now."

_names: dict[str, tuple[float, str | None]] = {}
_zips: dict[str, tuple[float, dict[str, tuple[str, str]]]] = {}
_lock = threading.Lock()


# ------------------------------------------------------------------------------------------------ google calls
@functools.lru_cache(maxsize=1)
def _session() -> AuthorizedSession:
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(credentials)


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    project = load_settings().project_id
    return {**({"X-Goog-User-Project": project} if project else {}), **(extra or {})}


def reverse_neighbourhood(lat: float, lon: float) -> str | None:
    """The neighbourhood Google Maps puts this point in, or None where it names none."""
    response = _session().get(
        GEOCODE_URL.format(lat=f"{lat:.5f}", lon=f"{lon:.5f}"),
        params=[("types", "neighborhood"), ("types", "sublocality"), ("languageCode", "en")],
        headers=_headers(), timeout=TIMEOUT_S,
    )
    response.raise_for_status()
    for result in response.json().get("results", []):
        for part in result.get("addressComponents", []):
            if set(part.get("types", [])) & NEIGHBOURHOOD_TYPES:
                return part.get("longText")
    return None


def search_place(query: str, near: tuple[float, float]) -> dict[str, Any] | None:
    """Places text search: the best match for a typed name, with its map bounds."""
    body = {"textQuery": query, "maxResultCount": 3, "languageCode": "en",
            "locationBias": {"circle": {"center": {"latitude": near[0], "longitude": near[1]}, "radius": BIAS_RADIUS_M}}}
    try:
        response = _session().post(PLACES_URL, json=body, timeout=TIMEOUT_S, headers=_headers({
            "X-Goog-FieldMask": "places.displayName,places.location,places.viewport,places.types"}))
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Places search failed: %s: %s", type(exc).__name__, exc)
        raise ToolError(LOOKUP_DOWN) from exc
    places = response.json().get("places", [])
    return places[0] if places else None


# ------------------------------------------------------------------------------------------------ BigQuery side
def zip_index() -> dict[str, tuple[str, str]]:
    """tract id -> (ZIP code, city), from BigQuery. Empty if the table has not been built."""
    with _lock:
        hit = _zips.get("all")
        if hit and time.monotonic() - hit[0] < NAME_TTL_S:
            return hit[1]
    settings = load_settings()
    try:
        rows = run_query(f"SELECT geo_id, zip_code, city FROM {table(settings, 'tract_areas')}", settings=settings, max_rows=20000)
    except ToolError:
        logger.warning("tract_areas is missing; run scripts/build_areas.sh. Areas fall back to tract numbers.")
        return {}
    index = {r["geo_id"]: (r["zip_code"], r["city"]) for r in rows}
    with _lock:
        _zips["all"] = (time.monotonic(), index)
    return index


# ------------------------------------------------------------------------------------------------ labelling
def display_label(neighbourhood: str | None, zip_code: str | None, city: str | None, geo_id: str) -> str:
    if neighbourhood and zip_code:
        return f"{neighbourhood} · {zip_code}"
    if zip_code:
        return f"ZIP {zip_code}" + (f" · {city}" if city else "")
    return f"Tract {str(geo_id)[-6:]}"


def _name_for(tract: dict[str, Any]) -> str | None:
    geo_id = tract["geo_id"]
    with _lock:
        hit = _names.get(geo_id)
        if hit and time.monotonic() - hit[0] < NAME_TTL_S:
            return hit[1]
    try:
        name = reverse_neighbourhood(tract["lat"], tract["lon"])
    except Exception as exc:  # one failed lookup should not lose the whole map
        logger.debug("reverse geocode failed for %s: %s", geo_id, type(exc).__name__)
        return None
    with _lock:
        _names[geo_id] = (time.monotonic(), name)
    return name


def annotate(tracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add zip, city, neighbourhood and a display label to every tract (in place)."""
    index = zip_index()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        names = list(pool.map(_name_for, tracts))
    named = sum(1 for n in names if n)
    logger.info("area names: %d of %d tracts have a Google Maps neighbourhood", named, len(tracts))
    for tract, name in zip(tracts, names):
        zip_code, city = index.get(tract["geo_id"], (None, None))
        tract.update(zip=zip_code, city=city, neighbourhood=name, area=display_label(name, zip_code, city, tract["geo_id"]))
    return tracts


# ------------------------------------------------------------------------------------------------ resolving a typed name
def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lat1, lon1), (lat2, lon2) = a, b
    h = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(h))


def tracts_in_view(tracts: list[dict[str, Any]], viewport: dict[str, Any] | None, point: tuple[float, float] | None) -> list[dict[str, Any]]:
    """Tracts whose centre is inside the map bounds, or within POINT_RADIUS_KM of a point place."""
    out = []
    for t in tracts:
        inside = False
        if viewport:
            lo, hi = viewport["low"], viewport["high"]
            inside = lo["latitude"] <= t["lat"] <= hi["latitude"] and lo["longitude"] <= t["lon"] <= hi["longitude"]
        if not inside and point and haversine_km(point, (t["lat"], t["lon"])) <= POINT_RADIUS_KM:
            inside = True
        if inside:
            out.append(t)
    return out


def known_areas(tracts: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    """Neighbourhoods that have measured-area tracts, biggest first. Used for suggestions and autocomplete."""
    groups: dict[str, dict[str, Any]] = {}
    for t in tracts:
        name = t.get("neighbourhood")
        if name:
            g = groups.setdefault(name, {"name": name, "tracts": 0, "people": 0})
            g["tracts"] += 1
            g["people"] += int(t.get("total_pop") or 0)
    return sorted(groups.values(), key=lambda g: -g["people"])[:limit]


def _clean(query: str) -> str:
    q = re.sub(r"\b(the|area|neighbou?rhood|district of)\b", " ", str(query or "").lower())
    return re.sub(r"\s+", " ", q).strip(" ,.?")


def resolve_area(query: str, tracts: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn what a person typed ("Oak Cliff", "75215", "Fair Park") into the measured-area tracts it covers."""
    q = _clean(query)
    if not q:
        return {"status": "not_found", "message": "Which area? Give a neighbourhood name or a ZIP code.", "suggestions": [a["name"] for a in known_areas(tracts, 6)]}

    zip_match = re.fullmatch(r"(?:zip(?: ?code)?)? ?(\d{5})", q)
    if zip_match:
        code = zip_match.group(1)
        chosen = [t for t in tracts if t.get("zip") == code]
        label, kind = f"ZIP {code}", "zip"
    else:
        # Names Google already gave our tracts need no second lookup.
        chosen = [t for t in tracts if t.get("neighbourhood") and q in t["neighbourhood"].lower()]
        label, kind = (chosen[0]["neighbourhood"] if chosen else q.title()), "neighbourhood"
        if not chosen:
            if not tracts:
                raise ToolError("No tracts are loaded.")
            centre = (sum(t["lat"] for t in tracts) / len(tracts), sum(t["lon"] for t in tracts) / len(tracts))
            place = search_place(f"{q}, {load_settings().city}", centre)
            if place:
                loc = place.get("location") or {}
                point = (loc["latitude"], loc["longitude"]) if loc else None
                is_area = bool(set(place.get("types", [])) & AREA_TYPES)
                chosen = tracts_in_view(tracts, place.get("viewport") if is_area else None, point)
                label, kind = (place.get("displayName") or {}).get("text") or q.title(), "place"
    if not chosen:
        return {"status": "not_found", "area": label,
                "message": f"No measured heat data covers {label}. The model only predicts inside the area the volunteers drove.",
                "suggestions": [a["name"] for a in known_areas(tracts, 6)]}
    return {"status": "ok", "label": label, "kind": kind, "tracts": chosen, "tract_count": len(chosen),
            "zip_codes": sorted({t["zip"] for t in chosen if t.get("zip")}), "source": "Google Maps" if kind != "zip" else "BigQuery"}
