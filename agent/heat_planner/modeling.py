"""The BigQuery ML offset model: how it is called, and the per-tract predictions every view shares.

The model predicts the *offset*: degrees F hotter (+) or cooler (-) than the campaign average. Feature construction
mirrors the training table built by the data lane (see agent/README.md); if they change features, change FEATURE_SQL
here and nowhere else.
"""

import functools
import logging
import time
from typing import Any

from .bq import ToolError, run_query, table
from .config import load_settings

logger = logging.getLogger(__name__)

# How far outside the area volunteers drove (in degrees, roughly 5 km) we still answer.
COVERAGE_PAD_DEG = 0.05
MAX_TRACTS = 5000  # a metro area has well under this many census tracts
TRACT_CACHE_SECONDS = 600

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


def attributions(raw: Any) -> list[dict[str, Any]]:
    """Flatten ML.EXPLAIN_PREDICT's nested attributions, biggest effect first."""
    items = [
        {"feature": a["feature"], "effect_f": round(float(a["attribution"]), 2)}
        for a in (raw or [])
        if a.get("attribution") is not None
    ]
    return sorted(items, key=lambda a: abs(a["effect_f"]), reverse=True)


# Plain names for the model's inputs. The model's geographic terms (coordinates, their squares, distance from the centre) all
# say "where in the city", so they are shown as one driver instead of as jargon.
DRIVER_NAMES = {
    "latitude": "Location in the city", "longitude": "Location in the city", "lat_sq": "Location in the city", "lon_sq": "Location in the city",
    "lat_lon": "Location in the city", "dist_center_km": "Location in the city",
    "poverty_rate": "Poverty rate", "no_vehicle_rate": "Households without a car", "median_age": "Median age",
    "median_year_structure_built": "Age of housing", "total_pop": "Population",
}


def group_drivers(drivers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine drivers that share a plain name, biggest effect first."""
    grouped: dict[str, float] = {}
    for d in drivers:
        name = DRIVER_NAMES.get(d["feature"], d["feature"])
        grouped[name] = grouped.get(name, 0.0) + d["effect_f"]
    return sorted(({"feature": k, "effect_f": round(v, 2)} for k, v in grouped.items()), key=lambda d: -abs(d["effect_f"]))


_tract_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def clear_tract_cache() -> None:
    _tract_cache.clear()


def predict_all_tracts() -> list[dict[str, Any]]:
    """ML.EXPLAIN_PREDICT for every census tract centroid inside the measured area, with its demographics."""
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
