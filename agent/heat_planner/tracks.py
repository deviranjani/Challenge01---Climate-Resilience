"""The three tracks of the challenge, and the decision each one makes.

Everything here is a pure function of the per-tract data (tracts.load_tracts), so it can be tested without BigQuery and
the numbers a judge sees can be traced to a formula. Predicted offset is degrees F above the campaign average.
"""

import statistics
from typing import Any

from .areas import haversine_km

TRACKS: dict[str, dict[str, Any]] = {
    "today": {
        "id": "today", "title": "Today", "subtitle": "Emergency response", "who": "City emergency management",
        "question": "It is 102°F tomorrow. Where do hydration trucks, wellness checks and extended library hours go first?",
        "problem": "Heat is most dangerous for people who cannot leave it: older residents, households without a car, people in the "
                   "hottest blocks. Dispatch has a few trucks and a few hours, so the question is which areas, in what order, and why.",
        "solution": "We rank Dallas areas by how much hotter the model predicts they run than the city average, combined with who is "
                    "least able to cope, and give a plain reason for every stop.",
        "output": "A ranked dispatch list by area, with the reason for each stop and a check on who it reaches.",
        "data": ["NOAA Heat Watch street-level temperatures", "Census (ACS) population, age, poverty and car access", "Census ZIP code areas"],
        "live_api": "Tomorrow's forecast high comes from the National Weather Service.",
        "cannot_do": ["The heat readings are from one afternoon, so this ranks places; it does not forecast.",
                      "It cannot see who lives alone or has no air conditioning; age and car access are stand-ins."],
    },
    "budget": {
        "id": "budget", "title": "This budget cycle", "subtitle": "Cooling centers", "who": "City planning, answerable to a council",
        "question": "We can fund three permanent cooling centers. Where should they go?",
        "problem": "A permanent building has to serve many heat-exposed residents, often, and without two centers competing for the same "
                   "neighbourhood. It also has to survive a council meeting: why here, who does it reach, and how often does it matter.",
        "solution": "We pick sites that cover the most heat-exposed, vulnerable residents within walking distance, without double counting, "
                    "and show how often the city actually reaches dangerous heat from seven years of station history.",
        "output": "Proposed sites with people covered and why, how often the city gets this hot, an equity check and a draft council proposal.",
        "data": ["NOAA Heat Watch street-level temperatures", "Census (ACS) population, age, poverty and car access", "GHCN-Daily station history (days at 100°F)", "Census ZIP code areas"],
        "live_api": None,
        "cannot_do": ["Construction cost, land availability and what a site displaces are not in the data; the planner supplies a cost per center.",
                      "Coverage is straight-line distance, not walking routes."],
    },
    "trees": {
        "id": "trees", "title": "This decade", "subtitle": "Tree planting", "who": "Sustainability and urban forestry",
        "question": "Where would tree planting or cool pavement give the most relief?",
        "problem": "Planting is slow and permanent, so it should start where excess heat, many residents and past under-investment overlap, "
                   "and the plan should be checked against whether it repeats or repairs that history.",
        "solution": "We rank areas by excess heat, residents and poverty, and audit the result against the city as a whole.",
        "output": "A ranked planting program by area, what drives each area's heat, and an equity audit of the plan.",
        "data": ["NOAA Heat Watch street-level temperatures", "Census (ACS) population, age, poverty and car access", "Census ZIP code areas"],
        "live_api": None,
        "cannot_do": ["The analysis has no tree canopy or pavement data, so it cannot say whether planting or cool pavement fits an area.",
                      "Relief per dollar needs costs we do not have, and nothing here simulates what planting would change."],
    },
}

FOCUS = {
    "hydration": {"label": "Hydration trucks", "weights": {"heat": 0.5, "cars": 0.3, "age": 0.2}},
    "wellness": {"label": "Wellness checks", "weights": {"age": 0.4, "heat": 0.35, "poverty": 0.25}},
    "cooling_hours": {"label": "Extended library hours", "weights": {"heat": 0.4, "cars": 0.35, "people": 0.25}},
}
EXPOSED_OFFSET_F = 1.0   # "heat-exposed": predicted at least this much hotter than the city average


def zscores(values: list[float]) -> list[float]:
    spread = statistics.pstdev(values)
    if spread == 0:
        return [0.0] * len(values)
    mean = statistics.fmean(values)
    return [(v - mean) / spread for v in values]


def _pct(v: Any) -> str:
    return "n/a" if v is None else f"{v * 100:.0f}%"


def _site(rank: int, t: dict[str, Any], score: float, reason: str) -> dict[str, Any]:
    return {"rank": rank, "geo_id": t["geo_id"], "area": t["area"], "zip": t.get("zip"), "neighbourhood": t.get("neighbourhood"),
            "lat": t["lat"], "lon": t["lon"], "offset_f": t["offset_f"], "people": t.get("total_pop"), "median_age": t.get("median_age"),
            "poverty_rate": t.get("poverty_rate"), "no_vehicle_rate": t.get("no_vehicle_rate"), "score": round(score, 3), "reason": reason,
            "drivers": t.get("drivers", [])}


# ------------------------------------------------------------------------------------------------ equity audit
def equity_audit(chosen: list[dict[str, Any]], city: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare who lives in the chosen tracts with the city as a whole (population-weighted). Race is not used anywhere."""
    def avg(rows: list[dict[str, Any]], key: str) -> float | None:
        pairs = [(r[key], r.get("total_pop") or 0) for r in rows if r.get(key) is not None]
        weight = sum(w for _, w in pairs)
        return None if not weight else sum(v * w for v, w in pairs) / weight

    measures = [("poverty_rate", "Poverty rate", True), ("no_vehicle_rate", "Households without a car", True), ("median_age", "Median age", False)]
    rows = []
    for key, label, pct in measures:
        mine, base = avg(chosen, key), avg(city, key)
        ratio = None if not mine or not base else mine / base
        rows.append({"measure": label, "chosen": None if mine is None else round(mine, 3 if pct else 1),
                     "city": None if base is None else round(base, 3 if pct else 1), "percent": pct,
                     "verdict": "n/a" if ratio is None else "above the city" if ratio >= 1.15 else "below the city" if ratio <= 0.85 else "about the city average"})
    need = [r for r in rows if r["measure"] != "Median age"]
    above = sum(1 for r in need if r["verdict"] == "above the city")
    below = sum(1 for r in need if r["verdict"] == "below the city")
    if above == len(need):
        summary = "The chosen areas have more poverty and more households without a car than the city overall: the plan reaches vulnerable areas."
    elif below == len(need):
        summary = "The chosen areas are better off than the city overall: the model may be finding where it is hot, not where heat hurts most."
    else:
        summary = "Mixed: the chosen areas differ from the city on some measures but not others."
    return {"rows": rows, "summary": summary, "areas_compared": len(chosen), "city_tracts": len(city),
            "note": "Race and ethnicity are not model inputs. Median income is not available: the ACS income column loaded empty."}


# ------------------------------------------------------------------------------------------------ track 1: today
def today_sites(tracts: list[dict[str, Any]], focus: str = "hydration", top_n: int = 10) -> dict[str, Any]:
    focus = focus if focus in FOCUS else "hydration"
    spec = FOCUS[focus]
    usable = [t for t in tracts if t.get("no_vehicle_rate") is not None and t.get("median_age") is not None and t.get("poverty_rate") is not None]
    if not usable:
        return {"status": "error", "message": "No tracts have the demographics needed to rank them."}
    z = {"heat": zscores([t["offset_f"] for t in usable]), "cars": zscores([t["no_vehicle_rate"] for t in usable]),
         "age": zscores([t["median_age"] for t in usable]), "poverty": zscores([t["poverty_rate"] for t in usable]),
         "people": zscores([float(t.get("total_pop") or 0) for t in usable])}
    scored = sorted(((sum(w * z[k][i] for k, w in spec["weights"].items()), t) for i, t in enumerate(usable)), key=lambda p: -p[0])
    sites = [_site(i + 1, t, s, f"{t['offset_f']:+.1f}°F vs. average · {_pct(t.get('no_vehicle_rate'))} without a car · median age {t['median_age']:.0f} · {t.get('total_pop') or 0:,} people")
             for i, (s, t) in enumerate(scored[:top_n])]
    chosen = [t for _, t in scored[:top_n]]
    formula = " + ".join(f"{w:g}×{k}" for k, w in spec["weights"].items())
    return {"status": "ok", "track": "today", "focus": focus, "focus_label": spec["label"], "sites": sites,
            "method": f"score = {formula} (each measure as a z-score across tracts)", "audit": equity_audit(chosen, tracts)}


# ------------------------------------------------------------------------------------------------ track 2: budget cycle
def _need(t: dict[str, Any]) -> float:
    """Heat-exposed vulnerable people: residents × predicted excess heat × (1 + poverty + no-car)."""
    return (t.get("total_pop") or 0) * max(t["offset_f"], 0.0) * (1 + (t.get("poverty_rate") or 0) + (t.get("no_vehicle_rate") or 0))


def cooling_centers(tracts: list[dict[str, Any]], count: int = 3, radius_km: float = 1.5, cost_per_center: float | None = None) -> dict[str, Any]:
    weights = {t["geo_id"]: _need(t) for t in tracts}
    total_need = sum(weights.values())
    if total_need <= 0:
        return {"status": "error", "message": "No tract is predicted hotter than average, so there is nothing to cover."}
    covered: set[str] = set()
    centers, chosen_tracts = [], []
    for rank in range(1, count + 1):
        best, best_gain, best_members = None, 0.0, []
        for c in tracts:
            members = [t for t in tracts if t["geo_id"] not in covered and haversine_km((c["lat"], c["lon"]), (t["lat"], t["lon"])) <= radius_km]
            gain = sum(weights[t["geo_id"]] for t in members)
            if gain > best_gain:
                best, best_gain, best_members = c, gain, members
        if best is None:
            break
        covered.update(t["geo_id"] for t in best_members)
        chosen_tracts.extend(best_members)
        people = sum(t.get("total_pop") or 0 for t in best_members)
        hot_weight = sum(max(t["offset_f"], 0) * (t.get("total_pop") or 0) for t in best_members)
        centers.append({**_site(rank, best, best_gain / total_need, f"covers {people:,} people in {len(best_members)} tracts within {radius_km:g} km"),
                        "people_covered": people, "tracts_covered": len(best_members), "share_of_need": round(best_gain / total_need, 3),
                        "avg_offset_f": round(hot_weight / people, 2) if people else None})
    exposed = [t for t in tracts if t["offset_f"] >= EXPOSED_OFFSET_F]
    exposed_people = sum(t.get("total_pop") or 0 for t in exposed)
    exposed_covered = sum(t.get("total_pop") or 0 for t in exposed if t["geo_id"] in covered)
    return {"status": "ok", "track": "budget", "centers": centers, "radius_km": radius_km, "count": len(centers),
            "people_covered": sum(c["people_covered"] for c in centers), "share_of_need_covered": round(sum(c["share_of_need"] for c in centers), 3),
            "heat_exposed_people": exposed_people, "heat_exposed_covered": exposed_covered,
            "total_cost_usd": None if cost_per_center is None else round(cost_per_center * len(centers), 2),
            "cost_note": "Cost and land use are not in the data. Give a cost per center to total it; what a site displaces needs parcel data.",
            "method": "Each site is the tract centre that covers the most not-yet-covered need within the radius. need = people × predicted excess heat × (1 + poverty + no-car share).",
            "audit": equity_audit(chosen_tracts, tracts)}


# ------------------------------------------------------------------------------------------------ track 3: tree planting
def planting_sites(tracts: list[dict[str, Any]], top_n: int = 8) -> dict[str, Any]:
    scored = sorted(((_need_trees(t), t) for t in tracts), key=lambda p: -p[0])
    scored = [p for p in scored if p[0] > 0]
    if not scored:
        return {"status": "error", "message": "No tract is predicted hotter than average."}
    total = sum(s for s, _ in scored)
    sites = []
    for i, (s, t) in enumerate(scored[:top_n]):
        site = _site(i + 1, t, s / total, f"{t['offset_f']:+.1f}°F vs. average · {t.get('total_pop') or 0:,} people · poverty {_pct(t.get('poverty_rate'))}")
        site.update(share_of_priority=round(s / total, 3), intervention="undetermined",
                    intervention_note="No canopy or pavement data is loaded, so the model cannot say whether planting or cool pavement fits.")
        sites.append(site)
    chosen = [t for _, t in scored[:top_n]]
    return {"status": "ok", "track": "trees", "sites": sites, "share_of_priority": round(sum(s["share_of_priority"] for s in sites), 3),
            "method": "priority = people × predicted excess heat × (1 + poverty rate)",
            "limits": TRACKS["trees"]["cannot_do"], "audit": equity_audit(chosen, tracts)}


def _need_trees(t: dict[str, Any]) -> float:
    return (t.get("total_pop") or 0) * max(t["offset_f"], 0.0) * (1 + (t.get("poverty_rate") or 0))
