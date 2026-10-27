"""Who lives in an area: census demographics, compared with the city."""

from typing import Any

from .. import tracts
from ._areas import resolve, weighted, where
from ._common import SOURCES, safe_tool


def _r(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


@safe_tool
def community_profile(area: str) -> dict[str, Any]:
    """Describe the people living in a named area, and how that compares with the city.

    Args:
        area: A neighbourhood name such as "Oak Cliff", or a five-digit ZIP code in Dallas.

    Returns:
        A dict with status, the resolved area name, population, median age, poverty rate and share of households without
        a car, each next to the city figure. Race and ethnicity are not used.
    """
    m = resolve(area)
    if m["status"] != "ok":
        return m
    rows, city = m["tracts"], tracts.load_tracts()
    mine = {k: weighted(rows, k) for k in ("median_age", "poverty_rate", "no_vehicle_rate")}
    base = {k: weighted(city, k) for k in mine}
    return {"status": "ok", "area": m["label"], "zip_codes": m["zip_codes"], "tracts": m["tract_count"],
            "total_population": sum(t.get("total_pop") or 0 for t in rows),
            "median_age": _r(mine["median_age"], 1), "poverty_rate": _r(mine["poverty_rate"], 3), "no_vehicle_rate": _r(mine["no_vehicle_rate"], 3),
            "city": {"median_age": _r(base["median_age"], 1), "poverty_rate": _r(base["poverty_rate"], 3), "no_vehicle_rate": _r(base["no_vehicle_rate"], 3)},
            "center": where(rows)["center"], "tract_ids": where(rows)["tract_ids"], "sources": SOURCES,
            "note": "Population-weighted tract averages, measured area only. Race and ethnicity are not used by design."}
