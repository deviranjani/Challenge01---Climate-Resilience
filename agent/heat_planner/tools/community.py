"""Who lives around a place: census-tract demographics."""

from typing import Any

from google.cloud import bigquery

from ..bq import ToolError, run_query, table
from ..config import load_settings
from ._common import clamp_int, safe_tool, validate_coordinates


@safe_tool
def community_profile(latitude: float, longitude: float, radius_km: int = 2) -> dict[str, Any]:
    """Describe the people living around a location using census-tract data.

    Args:
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.
        radius_km: Search radius in kilometres, 1 to 10. Defaults to 2.

    Returns:
        A dict with status, tracts_in_radius, total_population, and population-weighted
        median age, poverty rate and share of households without a car.
    """
    lat, lon = validate_coordinates(latitude, longitude)
    radius = clamp_int(radius_km, 1, 10, "radius_km")
    settings = load_settings()
    rows = run_query(
        f"""SELECT COUNT(*) AS tracts,
                   SUM(total_pop) AS people,
                   SAFE_DIVIDE(SUM(IF(median_age > 0, median_age * total_pop, NULL)),
                               SUM(IF(median_age > 0, total_pop, NULL))) AS median_age,
                   SAFE_DIVIDE(SUM(poverty_rate * total_pop), SUM(total_pop)) AS poverty_rate,
                   SAFE_DIVIDE(SUM(no_vehicle_rate * total_pop), SUM(total_pop)) AS no_vehicle_rate
            FROM {table(settings, 'tract_demographics')}
            WHERE ST_DWITHIN(ST_GEOGPOINT(tract_lon, tract_lat),
                             ST_GEOGPOINT(@lon, @lat), @meters)""",
        [bigquery.ScalarQueryParameter("lat", "FLOAT64", lat),
         bigquery.ScalarQueryParameter("lon", "FLOAT64", lon),
         bigquery.ScalarQueryParameter("meters", "FLOAT64", radius * 1000.0)],
        settings,
    )
    row = rows[0] if rows else {}
    if not row.get("tracts"):
        raise ToolError(f"No census tracts found within {radius} km of that location.")

    def rounded(value: Any, digits: int) -> Any:
        return None if value is None else round(float(value), digits)

    return {
        "status": "ok",
        "radius_km": radius,
        "tracts_in_radius": int(row["tracts"]),
        "total_population": int(row["people"] or 0),
        "median_age": rounded(row["median_age"], 1),
        "poverty_rate": rounded(row["poverty_rate"], 3),
        "no_vehicle_rate": rounded(row["no_vehicle_rate"], 3),
        "note": "Population-weighted averages of tract values. Race and ethnicity are not used by design.",
    }
