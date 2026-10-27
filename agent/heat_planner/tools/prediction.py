"""Tools for the Today track and for any "how hot is this area" question. Predictions come from BigQuery ML."""

from typing import Any

from .. import tracks, tracts
from ._areas import resolve, weighted, where
from ._common import CAVEATS, SOURCES, clamp_int, safe_tool

MAX_RANKED_SITES = 25


@safe_tool
def predict_heat_offset(area: str) -> dict[str, Any]:
    """How much hotter or cooler an area is predicted to run than the city average, and why.

    Use this for any question about a named place: a neighbourhood such as "Oak Cliff" or "Deep Ellum", or a ZIP code
    such as "75215". The prediction is made for each census tract in the area and averaged by population.

    Args:
        area: A neighbourhood name or a five-digit ZIP code in Dallas.

    Returns:
        A dict with status. On "ok": the resolved area name, predicted_offset_f (degrees F vs. the city average),
        the range across the area's tracts, the main drivers, and who lives there. On "not_found": suggestions.
    """
    m = resolve(area)
    if m["status"] != "ok":
        return m
    rows = m["tracts"]
    people = sum(t.get("total_pop") or 0 for t in rows)
    offset = weighted(rows, "offset_f")
    effects: dict[str, float] = {}
    for t in rows:
        for d in t.get("drivers", []):
            effects[d["feature"]] = effects.get(d["feature"], 0.0) + d["effect_f"] * (t.get("total_pop") or 0)
    drivers = sorted(({"feature": k, "effect_f": round(v / people, 2)} for k, v in effects.items()), key=lambda d: -abs(d["effect_f"]))[:4] if people else []
    return {"status": "ok", "area": m["label"], "zip_codes": m["zip_codes"], "tracts": m["tract_count"], "people": people,
            "predicted_offset_f": round(offset, 2), "range_f": [min(t["offset_f"] for t in rows), max(t["offset_f"] for t in rows)],
            "drivers": drivers, "median_age": _r(weighted(rows, "median_age"), 1), "poverty_rate": _r(weighted(rows, "poverty_rate"), 3),
            "no_vehicle_rate": _r(weighted(rows, "no_vehicle_rate"), 3), "center": where(rows)["center"], "tract_ids": where(rows)["tract_ids"], "sources": SOURCES, "caveats": CAVEATS}


def _r(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


@safe_tool
def rank_response_sites(focus: str = "hydration", top_n: int = 5) -> dict[str, Any]:
    """Today track: rank Dallas areas for an emergency response on a hot day.

    Args:
        focus: What is being sent. "hydration" for hydration trucks, "wellness" for wellness checks on older residents,
            "cooling_hours" for extended library or community-center hours. Defaults to "hydration".
        top_n: How many areas to return, 1 to 25. Defaults to 5.

    Returns:
        A dict with status and a ranked list of sites, each with the area name, predicted heat, who lives there and a
        plain reason, plus an equity check of who the list reaches.
    """
    top_n = clamp_int(top_n, 1, MAX_RANKED_SITES, "top_n")
    result = tracks.today_sites(tracts.load_tracts(), focus if focus in tracks.FOCUS else "hydration", top_n)
    return {**result, "sources": SOURCES, "caveats": CAVEATS} if result["status"] == "ok" else result
