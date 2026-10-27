"""Tool for the Budget-cycle track: where permanent cooling centers should go."""

from typing import Any

from .. import tracks, tracts
from ._common import CAVEATS, SOURCES, clamp_float, clamp_int, safe_tool
from .history import heat_frequency


@safe_tool
def recommend_cooling_centers(count: int = 3, radius_km: float = 1.5, cost_per_center_usd: float | None = None) -> dict[str, Any]:
    """Budget-cycle track: choose where to put permanent cooling centers.

    Picks sites that cover the most heat-exposed, vulnerable residents within walking distance, without counting the same
    people twice, and adds how often the city actually reaches 100°F from seven years of station history.

    Args:
        count: How many centers can be funded, 1 to 8. Defaults to 3.
        radius_km: Walking distance each center serves, 0.5 to 5 km. Defaults to 1.5.
        cost_per_center_usd: Optional planner-supplied cost per center. Cost and land use are not in the data.

    Returns:
        A dict with status and the proposed centers (area, people covered, why), the share of heat-exposed people
        covered, how often the city reaches 100°F, and an equity check.
    """
    count = clamp_int(count, 1, 8, "count")
    radius = clamp_float(radius_km, 0.5, 5.0, "radius_km")
    cost = None if cost_per_center_usd is None else clamp_float(cost_per_center_usd, 0, 1e9, "cost_per_center_usd")
    result = tracks.cooling_centers(tracts.load_tracts(), count, radius, cost)
    if result["status"] != "ok":
        return result
    days = heat_frequency(100)
    result["heat_days"] = None if days.get("status") != "ok" else {
        "threshold_f": 100, "average_days_per_year": days["average_days"], "peak_year": days["peak_year"], "peak_days": days["peak_days"], "trend": days["trend"]}
    return {**result, "sources": SOURCES, "caveats": CAVEATS}
