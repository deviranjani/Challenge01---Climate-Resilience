"""Data for the map and graph views: measured readings, per-tract predictions, and the tract graph.

The graph is built in memory from the same BigQuery tables the agent uses. It borrows the look of a
property graph (labelled nodes, typed relationships) without needing a graph database.
"""

import os
import threading
import time
from typing import Any

from .bq import ToolError, run_query, table
from .config import load_settings
from .tools.prediction import _attributions, predict_all_tracts

MAX_POINTS = 5000
CACHE_SECONDS = 600
GRAPH_DEFAULT_TRACTS = 80
GRAPH_MAX_TRACTS = 200

# Thresholds that turn numbers into graph categories. Shown to the user in the legend.
HOT_F, COOL_F = 1.0, -1.0
POVERTY_HIGH, POVERTY_LOW = 0.25, 0.10
NO_CAR_HIGH, NO_CAR_LOW = 0.20, 0.08
AGE_OLDER, AGE_YOUNGER = 40.0, 32.0

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _cached(key: str, load) -> Any:
    """Small in-process cache so panning a map never re-runs a BigQuery model call."""
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    value = load()
    with _lock:
        _cache[key] = (time.monotonic(), value)
    return value


def maps_config() -> dict[str, Any]:
    return {"mapsKey": os.environ.get("GOOGLE_MAPS_API_KEY", ""), "city": load_settings().city}


def _num(value: Any, digits: int) -> Any:
    return None if value is None else round(float(value), digits)


def measured_points(limit: int = MAX_POINTS) -> dict[str, Any]:
    """Street-level readings (a stable sample) with their offset from the campaign average."""
    limit = max(1, min(int(limit), MAX_POINTS))

    def load() -> dict[str, Any]:
        settings = load_settings()
        rows = run_query(
            f"""WITH m AS (SELECT AVG(temp_f) AS avg_f FROM {table(settings, 'heat_observations')})
                SELECT latitude, longitude, temp_f, temp_f - (SELECT avg_f FROM m) AS offset_f
                FROM {table(settings, 'heat_observations')}
                WHERE temp_f IS NOT NULL
                ORDER BY FARM_FINGERPRINT(CONCAT(CAST(latitude AS STRING), ',', CAST(longitude AS STRING)))
                LIMIT {MAX_POINTS}""",
            settings=settings,
            max_rows=MAX_POINTS,
        )
        if not rows:
            raise ToolError("No heat readings found; load the data first.")
        points = [{"lat": r["latitude"], "lon": r["longitude"], "temp_f": _num(r["temp_f"], 1),
                   "offset_f": _num(r["offset_f"], 2)} for r in rows]
        offsets = [p["offset_f"] for p in points]
        return {"points": points, "min_offset_f": min(offsets), "max_offset_f": max(offsets),
                "avg_temp_f": _num(sum(p["temp_f"] for p in points) / len(points), 1)}

    data = _cached("points", load)
    return {**data, "points": data["points"][:limit]}


def tract_predictions() -> list[dict[str, Any]]:
    """Every tract with the model's predicted offset, demographics and top drivers."""

    def load() -> list[dict[str, Any]]:
        out = []
        for r in predict_all_tracts():
            if r.get("predicted_offset_f") is None:
                continue
            out.append({
                "geo_id": r["geo_id"],
                "lat": r["latitude"], "lon": r["longitude"],
                "offset_f": _num(r["predicted_offset_f"], 2),
                "median_age": _num(r.get("median_age"), 1),
                "poverty_rate": _num(r.get("poverty_rate"), 3),
                "no_vehicle_rate": _num(r.get("no_vehicle_rate"), 3),
                "total_pop": None if r.get("total_pop") is None else int(r["total_pop"]),
                "drivers": _attributions(r.get("top_feature_attributions"))[:3],
            })
        if not out:
            raise ToolError("No tract predictions available; check the model and demographics tables.")
        return out

    return _cached("tracts", load)


def _band(value: float | None, high: float, low: float, labels: tuple[str, str, str]) -> str | None:
    if value is None:
        return None
    return labels[0] if value >= high else labels[2] if value <= low else labels[1]


def build_graph(tracts: list[dict[str, Any]], limit: int = GRAPH_DEFAULT_TRACTS) -> dict[str, Any]:
    """Tracts as nodes, linked to shared category nodes (heat, poverty, car access, age).

    Pure function: takes tract rows, returns {nodes, edges, legend}. The hottest `limit` tracts are kept
    so the picture stays readable.
    """
    limit = max(1, min(int(limit), GRAPH_MAX_TRACTS))
    chosen = sorted(tracts, key=lambda t: t["offset_f"], reverse=True)[:limit]

    categories = [
        ("HeatBand", "heat", "IN_HEAT_BAND", lambda t: _band(t["offset_f"], HOT_F, COOL_F, ("Hotter than average", "Near average", "Cooler than average"))),
        ("PovertyLevel", "poverty", "HAS_POVERTY", lambda t: _band(t["poverty_rate"], POVERTY_HIGH, POVERTY_LOW, ("High poverty", "Medium poverty", "Low poverty"))),
        ("CarAccess", "cars", "HAS_CAR_ACCESS", lambda t: _band(t["no_vehicle_rate"], NO_CAR_HIGH, NO_CAR_LOW, ("Many without a car", "Some without a car", "Most have a car"))),
        ("AgeBand", "age", "HAS_AGE", lambda t: _band(t["median_age"], AGE_OLDER, AGE_YOUNGER, ("Older population", "Middle-aged", "Younger population"))),
    ]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()

    for t in chosen:
        tract_id = f"tract:{t['geo_id']}"
        nodes.append({"id": tract_id, "label": "Tract", "name": str(t["geo_id"])[-6:], "group": "Tract",
                      "offset_f": t["offset_f"], "total_pop": t["total_pop"], "median_age": t["median_age"],
                      "poverty_rate": t["poverty_rate"], "no_vehicle_rate": t["no_vehicle_rate"],
                      "drivers": t["drivers"], "lat": t["lat"], "lon": t["lon"]})
        for label, _key, relation, pick in categories:
            name = pick(t)
            if name is None:
                continue
            cat_id = f"{label}:{name}"
            if cat_id not in seen:
                seen.add(cat_id)
                nodes.append({"id": cat_id, "label": label, "name": name, "group": label})
            edges.append({"from": tract_id, "to": cat_id, "type": relation})

    return {
        "nodes": nodes,
        "edges": edges,
        "tracts_shown": len(chosen),
        "tracts_total": len(tracts),
        "legend": {
            "heat": f"Hotter than average: offset >= +{HOT_F:g}F. Cooler: <= {COOL_F:g}F.",
            "poverty": f"High poverty: >= {POVERTY_HIGH:.0%}. Low: <= {POVERTY_LOW:.0%}.",
            "cars": f"Many without a car: >= {NO_CAR_HIGH:.0%} of households. Most have a car: <= {NO_CAR_LOW:.0%}.",
            "age": f"Older: median age >= {AGE_OLDER:g}. Younger: <= {AGE_YOUNGER:g}.",
        },
    }


def graph(limit: int = GRAPH_DEFAULT_TRACTS) -> dict[str, Any]:
    return build_graph(tract_predictions(), limit)
