"""Shared by the tools that take an area name instead of coordinates."""

from typing import Any

from .. import areas, tracts


def resolve(area: str) -> dict[str, Any]:
    """Resolve what the user typed to measured-area tracts, or a not_found result with suggestions."""
    return areas.resolve_area(area, tracts.load_tracts())


def weighted(rows: list[dict[str, Any]], key: str) -> float | None:
    pairs = [(r[key], r.get("total_pop") or 0) for r in rows if r.get(key) is not None]
    weight = sum(w for _, w in pairs)
    return None if not weight else sum(v * w for v, w in pairs) / weight


def where(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Population-weighted centre and tract ids of an area, so the map can fly to it."""
    weight = sum(r.get("total_pop") or 0 for r in rows) or len(rows)
    w = lambda r: (r.get("total_pop") or 0) or 1  # noqa: E731
    return {"center": {"lat": round(sum(r["lat"] * w(r) for r in rows) / sum(w(r) for r in rows), 5), "lon": round(sum(r["lon"] * w(r) for r in rows) / sum(w(r) for r in rows), 5)},
            "tract_ids": [r["geo_id"] for r in rows], "weight": weight}
