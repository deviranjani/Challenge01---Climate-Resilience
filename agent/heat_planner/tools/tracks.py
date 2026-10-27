"""Three-Track Decision Tools with operational guardrails for the City of Dallas:
- Track 1 (Today): Emergency dispatch of <= 20 hydration trucks (multi-unit scaling + fire engine misting)
  and <= 10 mobile wellness check units.
- Track 2 (This Budget Cycle): Siting <= 3 permanent cooling centers + nearest Dallas Public Library
  as a supplementary cooling center.
- Track 3 (This Decade): 10-year tree canopy planting priority plan for peak-time natural relief.
"""

import math
from typing import Any

from .. import config
from ..bq import ToolError, run_query, table
from ..config import Settings, load_settings
from ._common import CAVEATS, clamp_int, safe_tool
from .prediction import FEATURE_SQL, _attributions, _zscores, score_sites

MODELING_GUARDRAIL = (
    "ML.EXPLAIN_PREDICT diagnoses where peak afternoon heat is worst and which urban/demographic "
    "features drive it; it is a diagnostic spatial model, not a counterfactual post-planting simulation."
)

# Reference Dallas Public Library branches used as supplementary cooling centers in Track 2.
DALLAS_LIBRARIES: tuple[dict[str, Any], ...] = (
    {"name": "J. Erik Jonsson Central Library", "address": "1515 Young St, Dallas, TX 75201", "latitude": 32.7763, "longitude": -96.7979},
    {"name": "Martin Luther King Jr. Branch Library", "address": "2922 MLK Jr Blvd, Dallas, TX 75215", "latitude": 32.7669, "longitude": -96.7667},
    {"name": "Dallas West Branch Library", "address": "2332 Singleton Blvd, Dallas, TX 75212", "latitude": 32.7785, "longitude": -96.8580},
    {"name": "Arcadia Park Branch Library", "address": "1302 N Justin Ave, Dallas, TX 75211", "latitude": 32.7580, "longitude": -96.8981},
    {"name": "Oak Lawn Branch Library", "address": "4100 Cedar Springs Rd, Dallas, TX 75219", "latitude": 32.8112, "longitude": -96.8116},
    {"name": "North Oak Cliff Branch Library", "address": "302 W Tenth St, Dallas, TX 75208", "latitude": 32.7458, "longitude": -96.8266},
    {"name": "Hampton-Illinois Branch Library", "address": "2951 S Hampton Rd, Dallas, TX 75224", "latitude": 32.7166, "longitude": -96.8569},
    {"name": "Lancaster-Kiest Branch Library", "address": "2008 E Kiest Blvd, Dallas, TX 75216", "latitude": 32.7077, "longitude": -96.7924},
    {"name": "Polk-Wisdom Branch Library", "address": "7151 Library Ln, Dallas, TX 75232", "latitude": 32.6621, "longitude": -96.8407},
    {"name": "Pleasant Grove Branch Library", "address": "7310 Lake June Rd, Dallas, TX 75217", "latitude": 32.7345, "longitude": -96.6939},
    {"name": "Skyline Branch Library", "address": "6006 Everglade Rd, Dallas, TX 75227", "latitude": 32.7937, "longitude": -96.6873},
    {"name": "Paul Laurence Dunbar Lancaster-Kiest Library", "address": "2008 E Kiest Blvd, Dallas, TX 75216", "latitude": 32.7082, "longitude": -96.7918},
    {"name": "Bachman Lake Branch Library", "address": "9480 Webb Chapel Rd, Dallas, TX 75220", "latitude": 32.8596, "longitude": -96.8726},
    {"name": "Grauwyler Park Branch Library", "address": "2146 Gilford St, Dallas, TX 75235", "latitude": 32.8282, "longitude": -96.8427},
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_earth = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r_earth * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearest_library(lat: float, lon: float) -> dict[str, Any]:
    """Return the closest Dallas Public Library branch to use as a supplementary cooling center."""
    best = min(
        DALLAS_LIBRARIES,
        key=lambda lib: _haversine_km(lat, lon, lib["latitude"], lib["longitude"]),
    )
    dist = _haversine_km(lat, lon, best["latitude"], best["longitude"])
    return {
        "name": best["name"],
        "address": best["address"],
        "latitude": best["latitude"],
        "longitude": best["longitude"],
        "distance_km": round(dist, 2),
        "role": "Supplementary cooling center (existing public library)",
    }


def _fetch_tract_predictions(settings: Settings) -> list[dict[str, Any]]:
    features = FEATURE_SQL.format(lat="t.tract_lat", lon="t.tract_lon")
    sql = f"""
    WITH c AS (SELECT AVG(latitude) AS clat, AVG(longitude) AS clon
               FROM {table(settings, 'heat_observations')})
    SELECT * FROM ML.EXPLAIN_PREDICT(
      MODEL {table(settings, settings.model_name)},
      (SELECT t.geo_id, {features},
              t.median_age, t.median_year_structure_built,
              t.poverty_rate, t.no_vehicle_rate, t.total_pop
       FROM {table(settings, 'tract_demographics')} t, c
       WHERE t.tract_lat IS NOT NULL AND t.tract_lon IS NOT NULL),
      STRUCT(3 AS top_k_features))"""
    return run_query(sql, settings=settings)


def allocate_hydration_trucks(scored: list[dict[str, Any]], max_trucks: int) -> list[dict[str, Any]]:
    """Allocate up to max_trucks across highest-priority tracts, scaling units by heat & population."""
    remaining = max_trucks
    dispatches: list[dict[str, Any]] = []
    for site in scored:
        if remaining <= 0:
            break
        offset = float(site["predicted_offset_f"])
        pop = int(site.get("total_pop") or 0)
        desired = 3 if (offset >= 3.5 and pop >= 4500) else (2 if (offset >= 2.2 or pop >= 4000) else 1)
        assigned = min(desired, remaining)
        remaining -= assigned
        fire_support = offset >= 2.5 or assigned >= 2
        reason = (
            f"Co-dispatch Dallas Fire-Rescue engine for hydrant misting/cooling (+{offset:.2f}F offset, {pop:,} residents)."
            if fire_support
            else None
        )
        dispatches.append({
            **site,
            "trucks_assigned": assigned,
            "fire_engine_support": fire_support,
            "fire_dispatch_reason": reason,
        })
    return dispatches


def score_wellness_sites(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank tracts for mobile wellness checks using heat, age, no-car rate, and older housing."""
    usable = [
        r for r in rows
        if r.get("predicted_offset_f") is not None
        and r.get("no_vehicle_rate") is not None
        and r.get("median_age") is not None
    ]
    if not usable:
        return []
    heat = _zscores([float(r["predicted_offset_f"]) for r in usable])
    age = _zscores([float(r["median_age"]) for r in usable])
    cars = _zscores([float(r["no_vehicle_rate"]) for r in usable])
    older = _zscores([-float(r.get("median_year_structure_built") or 1980) for r in usable])
    scored = []
    for r, h, a, c, o in zip(usable, heat, age, cars, older):
        scored.append({
            "geo_id": r.get("geo_id"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "predicted_offset_f": round(float(r["predicted_offset_f"]), 2),
            "median_age": round(float(r["median_age"]), 1),
            "no_vehicle_rate": round(float(r["no_vehicle_rate"]), 3),
            "poverty_rate": round(float(r.get("poverty_rate") or 0.0), 3),
            "median_year_structure_built": int(r.get("median_year_structure_built") or 1980),
            "total_pop": int(r.get("total_pop") or 0),
            "wellness_priority_score": round(0.35 * h + 0.25 * a + 0.20 * c + 0.20 * o, 3),
            "top_drivers": _attributions(r.get("top_feature_attributions"))[:3],
        })
    return sorted(scored, key=lambda s: s["wellness_priority_score"], reverse=True)


@safe_tool
def dispatch_today_fleet(hydration_trucks: int = 20, wellness_units: int = 10) -> dict[str, Any]:
    """Track 1 (Today): Dispatch hydration trucks (with fire-engine support) and mobile wellness checks.

    Enforces Dallas operational caps: at most 20 hydration trucks (assigning multiple trucks to
    large/severe heat zones and flagging fire engine misting support) and at most 10 mobile
    wellness check units.

    Args:
        hydration_trucks: Total hydration trucks to deploy across Dallas, 1 to 20. Defaults to 20.
        wellness_units: Total mobile wellness check units to deploy, 1 to 10. Defaults to 10.
    """
    trucks_cap = clamp_int(hydration_trucks, 1, config.MAX_HYDRATION_TRUCKS, "hydration_trucks")
    wellness_cap = clamp_int(wellness_units, 1, config.MAX_WELLNESS_UNITS, "wellness_units")
    settings = load_settings()
    rows = _fetch_tract_predictions(settings)
    scored_hydration = score_sites(rows, weights=(0.55, 0.30, 0.15))
    scored_wellness = score_wellness_sites(rows)
    if not scored_hydration or not scored_wellness:
        raise ToolError("No tracts could be scored for Track 1 dispatch.")

    dispatches = allocate_hydration_trucks(scored_hydration, trucks_cap)
    deployed = sum(d["trucks_assigned"] for d in dispatches)
    fire_zones = sum(1 for d in dispatches if d["fire_engine_support"])
    return {
        "status": "ok",
        "track": "Track 1 — Today (Emergency Dispatch)",
        "guardrails": {
            "max_hydration_trucks": config.MAX_HYDRATION_TRUCKS,
            "max_wellness_units": config.MAX_WELLNESS_UNITS,
            "multi_truck_scaling": "1-3 hydration trucks per zone scaled by heat offset and population",
            "fire_engine_policy": "Dallas Fire-Rescue engine co-dispatched for misting when offset >= +2.5F or >= 2 trucks assigned",
        },
        "hydration_summary": {
            "trucks_requested": trucks_cap,
            "trucks_deployed": deployed,
            "zones_served": len(dispatches),
            "fire_engine_co_dispatches": fire_zones,
        },
        "hydration_dispatches": dispatches,
        "wellness_checks": scored_wellness[:wellness_cap],
        "caveats": CAVEATS,
    }


def _score_cooling_centers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable = [
        r for r in rows
        if r.get("predicted_offset_f") is not None
        and r.get("no_vehicle_rate") is not None
        and r.get("poverty_rate") is not None
    ]
    if not usable:
        return []
    heat = _zscores([float(r["predicted_offset_f"]) for r in usable])
    cars = _zscores([float(r["no_vehicle_rate"]) for r in usable])
    pov = _zscores([float(r["poverty_rate"]) for r in usable])
    pop = _zscores([float(r.get("total_pop") or 0) for r in usable])
    scored = []
    for r, h, c, p, pop_z in zip(usable, heat, cars, pov, pop):
        lat = float(r.get("latitude") or 32.7767)
        lon = float(r.get("longitude") or -96.7970)
        scored.append({
            "geo_id": r.get("geo_id"),
            "latitude": lat,
            "longitude": lon,
            "predicted_offset_f": round(float(r["predicted_offset_f"]), 2),
            "no_vehicle_rate": round(float(r["no_vehicle_rate"]), 3),
            "poverty_rate": round(float(r["poverty_rate"]), 3),
            "median_age": round(float(r.get("median_age") or 0.0), 1),
            "total_pop": int(r.get("total_pop") or 0),
            "cooling_benefit_score": round(0.40 * h + 0.25 * c + 0.20 * p + 0.15 * pop_z, 3),
            "nearest_library": find_nearest_library(lat, lon),
            "top_drivers": _attributions(r.get("top_feature_attributions"))[:3],
        })
    return sorted(scored, key=lambda s: s["cooling_benefit_score"], reverse=True)


@safe_tool
def recommend_cooling_centers(max_centers: int = 3) -> dict[str, Any]:
    """Track 2 (This Budget Cycle): Recommend up to 3 permanent cooling centers + nearest library.

    Enforces the strict budget cap of at most 3 permanent cooling centers and pairs each site
    with its nearest Dallas Public Library branch as a supplementary cooling location.

    Args:
        max_centers: Number of permanent cooling centers to site, 1 to 3. Defaults to 3.
    """
    cap = clamp_int(max_centers, 1, config.MAX_COOLING_CENTERS, "max_centers")
    settings = load_settings()
    rows = _fetch_tract_predictions(settings)
    ranked = _score_cooling_centers(rows)
    if not ranked:
        raise ToolError("No tracts could be scored for Track 2 cooling centers.")

    freq_rows = run_query(
        f"""SELECT AVG(annual_days) AS avg_hot_days, COUNT(*) AS years_observed
            FROM (
              SELECT EXTRACT(YEAR FROM observation_date) AS yr,
                     COUNT(DISTINCT observation_date) AS annual_days
              FROM {table(settings, 'station_daily_temps')}
              WHERE max_temp_f >= 100.0
              GROUP BY yr
            )""",
        settings=settings,
    )
    freq = freq_rows[0] if freq_rows else {}
    avg_hot_days = round(float(freq.get("avg_hot_days") or 0.0), 1)
    return {
        "status": "ok",
        "track": "Track 2 — This Budget Cycle (Permanent Cooling Centers)",
        "guardrails": {
            "max_permanent_cooling_centers": config.MAX_COOLING_CENTERS,
            "supplementary_cooling_policy": "Each permanent site is paired with the nearest Dallas Public Library branch for overflow/immediate cooling.",
        },
        "regional_context": {
            "avg_days_ge_100f_per_year": avg_hot_days,
            "years_observed": int(freq.get("years_observed") or 0),
        },
        "cooling_centers": ranked[:cap],
        "caveats": CAVEATS,
    }


def _recommend_canopy_action(offset_f: float, drivers: list[dict[str, Any]], year_built: int) -> str:
    top_feat = drivers[0]["feature"] if drivers else "urban_surface"
    if offset_f >= 3.0:
        return (
            f"High-intensity street-tree & transit-corridor canopy planting (primary driver: {top_feat}; "
            f"median structure year {year_built}) to shade impervious surfaces during 2pm-6pm peak heat."
        )
    return (
        f"Residential right-of-way and schoolyard shade canopy expansion (primary driver: {top_feat}; "
        f"median structure year {year_built}) for sustained afternoon heat relief."
    )


@safe_tool
def plan_tree_canopy(top_n: int = 5) -> dict[str, Any]:
    """Track 3 (This Decade): Rank areas where tree planting buys the most peak-time heat relief.

    Identifies census tracts where expanding tree cover over the next decade mitigates peak
    afternoon heat most effectively, grounded in ML.EXPLAIN_PREDICT attributions and housing age.

    Args:
        top_n: Number of priority canopy planting zones to return, 1 to 10. Defaults to 5.
    """
    cap = clamp_int(top_n, 1, config.MAX_CANOPY_ZONES, "top_n")
    settings = load_settings()
    rows = _fetch_tract_predictions(settings)
    usable = [
        r for r in rows
        if r.get("predicted_offset_f") is not None
        and r.get("poverty_rate") is not None
    ]
    if not usable:
        raise ToolError("No tracts could be scored for Track 3 tree canopy planning.")

    heat = _zscores([float(r["predicted_offset_f"]) for r in usable])
    older = _zscores([-float(r.get("median_year_structure_built") or 1980) for r in usable])
    pop = _zscores([float(r.get("total_pop") or 0) for r in usable])
    pov = _zscores([float(r["poverty_rate"]) for r in usable])

    zones = []
    for r, h, o, pop_z, p in zip(usable, heat, older, pop, pov):
        offset_f = round(float(r["predicted_offset_f"]), 2)
        year_built = int(r.get("median_year_structure_built") or 1980)
        drivers = _attributions(r.get("top_feature_attributions"))[:3]
        score = round(0.45 * h + 0.25 * o + 0.15 * pop_z + 0.15 * p, 3)
        zones.append({
            "geo_id": r.get("geo_id"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "predicted_offset_f": offset_f,
            "canopy_priority_score": score,
            "total_pop": int(r.get("total_pop") or 0),
            "poverty_rate": round(float(r["poverty_rate"]), 3),
            "median_year_structure_built": year_built,
            "dominant_drivers": drivers,
            "recommended_action": _recommend_canopy_action(offset_f, drivers, year_built),
        })
    zones.sort(key=lambda z: z["canopy_priority_score"], reverse=True)
    return {
        "status": "ok",
        "track": "Track 3 — This Decade (10-Year Tree Canopy Plan)",
        "method": "canopy_priority = 0.45*peak_heat + 0.25*older_housing + 0.15*population + 0.15*poverty (z-scores)",
        "modeling_guardrail": MODELING_GUARDRAIL,
        "canopy_zones": zones[:cap],
        "caveats": CAVEATS,
    }
