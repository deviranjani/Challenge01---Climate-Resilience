"""Tools that call the BigQuery ML offset model through ML.EXPLAIN_PREDICT.

The model predicts the *offset*: degrees F hotter (+) or cooler (-) than the campaign
average. Feature construction mirrors the training table built by the data lane
(see agent/README.md); if they change features, change FEATURE_SQL here and nowhere else.
"""

import functools
import logging
import statistics
import time
from typing import Any

from google.cloud import bigquery

from ..bq import ToolError, run_query, table
from ..config import load_settings
from ._common import CAVEATS, clamp_int, safe_tool, validate_coordinates

logger = logging.getLogger(__name__)

# How far outside the area volunteers drove (in degrees, roughly 5 km) we still answer.
COVERAGE_PAD_DEG = 0.05
TOP_K_FEATURES = 5
MAX_RANKED_SITES = 25
MAX_TRACTS = 5000  # a metro area has well under this many census tracts

# The census table uses -666666666 for "not available". Treat impossible values as missing; the
# model fills in missing inputs itself, so a bad tract degrades to an average guess, not garbage.
TRACT_CLEAN_SQL = (
    "IF(t.median_age > 0, t.median_age, NULL) AS median_age, "
    "IF(t.median_year_structure_built > 1800, t.median_year_structure_built, NULL) AS median_year_structure_built,"
)

# Feature columns the model was trained on. Order does not matter, names must match.
FEATURE_SQL = """
  {lat} AS latitude,
  {lon} AS longitude,
  ST_DISTANCE(ST_GEOGPOINT({lon}, {lat}), ST_GEOGPOINT(c.clon, c.clat)) / 1000 AS dist_center_km,
  POW({lat} - c.clat, 2) AS lat_sq,
  POW({lon} - c.clon, 2) AS lon_sq,
  ({lat} - c.clat) * ({lon} - c.clon) AS lat_lon
"""


@functools.lru_cache(maxsize=1)
def _coverage() -> dict[str, float]:
    """Bounding box of the street-level readings, used to refuse far-away questions."""
    settings = load_settings()
    rows = run_query(
        f"""SELECT MIN(latitude) AS lat_min, MAX(latitude) AS lat_max,
                   MIN(longitude) AS lon_min, MAX(longitude) AS lon_max
            FROM {table(settings, 'heat_observations')}""",
        settings=settings,
    )
    if not rows or rows[0]["lat_min"] is None:
        raise ToolError("heat_observations is empty; load the data first.")
    return rows[0]


def _within_coverage(lat: float, lon: float) -> bool:
    box = _coverage()
    return (
        box["lat_min"] - COVERAGE_PAD_DEG <= lat <= box["lat_max"] + COVERAGE_PAD_DEG
        and box["lon_min"] - COVERAGE_PAD_DEG <= lon <= box["lon_max"] + COVERAGE_PAD_DEG
    )


def _attributions(raw: Any) -> list[dict[str, Any]]:
    """Flatten ML.EXPLAIN_PREDICT's nested attributions, biggest effect first."""
    items = [
        {"feature": a["feature"], "effect_f": round(float(a["attribution"]), 2)}
        for a in (raw or [])
        if a.get("attribution") is not None
    ]
    return sorted(items, key=lambda a: abs(a["effect_f"]), reverse=True)


@safe_tool
def predict_heat_offset(latitude: float, longitude: float) -> dict[str, Any]:
    """Predict how much hotter or cooler a location is than the city's average, with reasons.

    Use this for any question about a specific place, including places nobody measured.
    Returns the predicted offset in degrees Fahrenheit and the features that drove it.

    Args:
        latitude: Latitude in decimal degrees, for example 32.78.
        longitude: Longitude in decimal degrees, for example -96.80.

    Returns:
        A dict with status ("ok", "out_of_coverage" or "error"). On "ok": predicted_offset_f,
        drivers (list of {feature, effect_f}, largest first), nearest-tract demographics and caveats.
    """
    lat, lon = validate_coordinates(latitude, longitude)
    if not _within_coverage(lat, lon):
        return {
            "status": "out_of_coverage",
            "message": "That location is outside the area covered by the heat readings, "
            "so the model cannot give a trustworthy prediction.",
        }

    settings = load_settings()
    features = FEATURE_SQL.format(lat="@lat", lon="@lon")
    sql = f"""
    WITH c AS (SELECT AVG(latitude) AS clat, AVG(longitude) AS clon
               FROM {table(settings, 'heat_observations')}),
    tract AS (
      SELECT * FROM {table(settings, 'tract_demographics')}
      ORDER BY ST_DISTANCE(ST_GEOGPOINT(tract_lon, tract_lat), ST_GEOGPOINT(@lon, @lat))
      LIMIT 1)
    SELECT * FROM ML.EXPLAIN_PREDICT(
      MODEL {table(settings, settings.model_name)},
      (SELECT {features},
              {TRACT_CLEAN_SQL}
              t.poverty_rate, t.no_vehicle_rate, t.total_pop
       FROM c, tract t),
      STRUCT({TOP_K_FEATURES} AS top_k_features))"""
    rows = run_query(
        sql,
        [bigquery.ScalarQueryParameter("lat", "FLOAT64", lat),
         bigquery.ScalarQueryParameter("lon", "FLOAT64", lon)],
        settings,
    )
    if not rows or rows[0].get("predicted_offset_f") is None:
        raise ToolError("The model returned no prediction for that location.")
    row = rows[0]
    return {
        "status": "ok",
        "latitude": lat,
        "longitude": lon,
        "predicted_offset_f": round(float(row["predicted_offset_f"]), 2),
        "drivers": _attributions(row.get("top_feature_attributions")),
        "nearest_tract": {
            "median_age": row.get("median_age"),
            "poverty_rate": row.get("poverty_rate"),
            "no_vehicle_rate": row.get("no_vehicle_rate"),
            "total_pop": row.get("total_pop"),
        },
        "caveats": CAVEATS,
    }


def _zscores(values: list[float]) -> list[float]:
    spread = statistics.pstdev(values)
    if spread == 0:
        return [0.0] * len(values)
    mean = statistics.fmean(values)
    return [(v - mean) / spread for v in values]


def score_sites(rows: list[dict[str, Any]], weights: tuple[float, float, float]) -> list[dict[str, Any]]:
    """Blend predicted heat with vulnerability. Pure function, so it is easy to test."""
    usable = [
        r for r in rows
        if r.get("predicted_offset_f") is not None
        and r.get("no_vehicle_rate") is not None
        and r.get("median_age") is not None
    ]
    if not usable:
        return []
    heat = _zscores([float(r["predicted_offset_f"]) for r in usable])
    cars = _zscores([float(r["no_vehicle_rate"]) for r in usable])
    age = _zscores([float(r["median_age"]) for r in usable])
    w_heat, w_cars, w_age = weights
    scored = []
    for r, h, c, a in zip(usable, heat, cars, age):
        scored.append({
            "geo_id": r.get("geo_id"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "predicted_offset_f": round(float(r["predicted_offset_f"]), 2),
            "no_vehicle_rate": round(float(r["no_vehicle_rate"]), 3),
            "median_age": r["median_age"],
            "total_pop": r.get("total_pop"),
            "priority_score": round(w_heat * h + w_cars * c + w_age * a, 3),
            "top_drivers": _attributions(r.get("top_feature_attributions"))[:3],
        })
    return sorted(scored, key=lambda s: s["priority_score"], reverse=True)


_tract_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
TRACT_CACHE_SECONDS = 600


def clear_tract_cache() -> None:
    _tract_cache.clear()


def predict_all_tracts() -> list[dict[str, Any]]:
    """The model's prediction for every census tract centroid, with its demographics.

    Shared by the ranking tool and the map and graph views, so there is one definition of
    "what the model says about a tract".
    """
    hit = _tract_cache.get("all")
    if hit and time.monotonic() - hit[0] < TRACT_CACHE_SECONDS:
        return hit[1]
    settings = load_settings()
    features = FEATURE_SQL.format(lat="t.tract_lat", lon="t.tract_lon")
    sql = f"""
    WITH c AS (SELECT AVG(latitude) AS clat, AVG(longitude) AS clon
               FROM {table(settings, 'heat_observations')})
    SELECT * FROM ML.EXPLAIN_PREDICT(
      MODEL {table(settings, settings.model_name)},
      (SELECT t.geo_id, {features},
              {TRACT_CLEAN_SQL}
              t.poverty_rate, t.no_vehicle_rate, t.total_pop
       FROM {table(settings, 'tract_demographics')} t, c
       WHERE t.tract_lat IS NOT NULL AND t.tract_lon IS NOT NULL),
      STRUCT(3 AS top_k_features))"""
    rows = run_query(sql, settings=settings, max_rows=MAX_TRACTS)
    # Far outside the measured roads the model's squared-coordinate features extrapolate wildly
    # (tens of degrees), so only tracts inside the measured area are returned.
    inside = [r for r in rows if r.get("latitude") is not None and _within_coverage(r["latitude"], r["longitude"])]
    logger.info("tract predictions: %d of %d tracts inside the measured area", len(inside), len(rows))
    _tract_cache["all"] = (time.monotonic(), inside)
    return inside


@safe_tool
def rank_response_sites(top_n: int = 5) -> dict[str, Any]:
    """Rank census tracts where heat relief should go first on a hot day.

    Combines the model's predicted heat offset with the share of households without a car
    and median age, so hot places where people cannot easily leave rank highest.

    Args:
        top_n: How many tracts to return, 1 to 25. Defaults to 5.

    Returns:
        A dict with status and a ranked list of sites (tract id, coordinates, predicted
        offset, vulnerability measures, priority score and top drivers).
    """
    top_n = clamp_int(top_n, 1, MAX_RANKED_SITES, "top_n")
    ranked = score_sites(predict_all_tracts(), weights=(0.5, 0.3, 0.2))
    if not ranked:
        raise ToolError("No tracts could be scored; check the model and demographics tables.")
    return {
        "status": "ok",
        "method": "priority = 0.5*heat + 0.3*no-vehicle rate + 0.2*median age (each as a z-score)",
        "sites": ranked[:top_n],
        "caveats": CAVEATS,
    }
