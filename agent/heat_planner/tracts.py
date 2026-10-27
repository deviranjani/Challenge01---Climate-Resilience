"""Every census tract inside the measured area, with the model's prediction, demographics and area name.

One definition of "what we know about a tract", shared by the map, the three tracks, the graph and the agent's tools.
"""

import threading
import time
from typing import Any

from . import areas, modeling

CACHE_SECONDS = 600
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_lock = threading.Lock()
_build = threading.Lock()  # one build at a time: the map, the tracks and the agent all ask at start-up


def clear_cache() -> None:
    with _lock:
        _cache.clear()
    modeling.clear_tract_cache()


def _num(value: Any, digits: int) -> Any:
    return None if value is None else round(float(value), digits)


def disambiguate(tracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Several census tracts can share a neighbourhood and ZIP. Where a label repeats, add the tract's last digits so every row is distinct."""
    counts: dict[str, int] = {}
    for t in tracts:
        counts[t["area"]] = counts.get(t["area"], 0) + 1
    for t in tracts:
        if counts[t["area"]] > 1:
            t["area"] = f"{t['area']} (tract {str(t['geo_id'])[-4:]})"
    return tracts


def _fresh() -> list[dict[str, Any]] | None:
    with _lock:
        hit = _cache.get("all")
        return hit[1] if hit and time.monotonic() - hit[0] < CACHE_SECONDS else None


def load_tracts() -> list[dict[str, Any]]:
    cached = _fresh()
    if cached is not None:
        return cached
    with _build:
        cached = _fresh()
        if cached is not None:
            return cached
        return _build_tracts()


def _build_tracts() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in modeling.predict_all_tracts():
        if r.get("predicted_offset_f") is None:
            continue
        out.append({
            "geo_id": r["geo_id"], "lat": r["latitude"], "lon": r["longitude"],
            "offset_f": _num(r["predicted_offset_f"], 2),
            "median_age": _num(r.get("median_age"), 1),
            "poverty_rate": _num(r.get("poverty_rate"), 3),
            "no_vehicle_rate": _num(r.get("no_vehicle_rate"), 3),
            "total_pop": None if r.get("total_pop") is None else int(r["total_pop"]),
            "drivers": modeling.group_drivers(modeling.attributions(r.get("top_feature_attributions"))[:3]),
        })
    areas.annotate(out)
    disambiguate(out)
    with _lock:
        _cache["all"] = (time.monotonic(), out)
    return out
