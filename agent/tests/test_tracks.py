import pytest

from heat_planner import tracks


def tract(geo_id, offset, pop=1000, poverty=0.15, cars=0.1, age=35.0, lat=32.75, lon=-96.80, area=None):
    return {"geo_id": geo_id, "lat": lat, "lon": lon, "offset_f": offset, "total_pop": pop, "poverty_rate": poverty, "no_vehicle_rate": cars,
            "median_age": age, "area": area or f"Area {geo_id}", "zip": "75201", "neighbourhood": None, "drivers": []}


def test_every_track_states_a_specific_problem_the_data_used_and_its_limits():
    assert set(tracks.TRACKS) == {"today", "budget", "trees"}
    for t in tracks.TRACKS.values():
        assert t["problem"] and t["solution"] and t["output"] and t["data"] and t["cannot_do"]
    assert tracks.TRACKS["today"]["live_api"] and "forecast" in tracks.TRACKS["today"]["live_api"]
    assert tracks.TRACKS["budget"]["live_api"] is None and tracks.TRACKS["trees"]["live_api"] is None


def test_today_ranks_hot_and_vulnerable_areas_first_with_a_reason():
    rows = [tract("a", 0.5, cars=0.02, age=28), tract("b", 3.0, cars=0.35, age=50), tract("c", 1.5, cars=0.12, age=36)]
    out = tracks.today_sites(rows, "hydration", 3)
    assert [s["geo_id"] for s in out["sites"]] == ["b", "c", "a"]
    assert "without a car" in out["sites"][0]["reason"] and out["sites"][0]["rank"] == 1


def test_each_focus_weights_differently():
    rows = [tract("old", 1.0, age=70, cars=0.02), tract("carless", 1.0, age=30, cars=0.4), tract("mid", 1.0, age=45, cars=0.1)]
    assert tracks.today_sites(rows, "wellness", 1)["sites"][0]["geo_id"] == "old"
    assert tracks.today_sites(rows, "hydration", 1)["sites"][0]["geo_id"] == "carless"
    assert tracks.today_sites(rows, "nonsense", 1)["focus"] == "hydration"  # unknown focus falls back


def test_cooling_centers_do_not_count_the_same_people_twice():
    # Two tracts sit on top of each other; a third is far away. Two centers must cover both clusters, not stack on one.
    rows = [tract("n1", 3.0, pop=5000, lat=32.80, lon=-96.80), tract("n2", 3.0, pop=5000, lat=32.8001, lon=-96.8001),
            tract("far", 2.0, pop=4000, lat=32.70, lon=-96.70)]
    out = tracks.cooling_centers(rows, count=2, radius_km=1.5)
    assert out["count"] == 2
    assert out["centers"][0]["people_covered"] == 10000 and out["centers"][1]["people_covered"] == 4000
    assert out["people_covered"] == 14000 and out["share_of_need_covered"] == pytest.approx(1.0, abs=0.01)


def test_cooling_centers_stop_when_nothing_is_left_to_cover_and_cost_is_never_invented():
    rows = [tract("only", 2.0, pop=3000)]
    out = tracks.cooling_centers(rows, count=3, radius_km=1.5)
    assert out["count"] == 1 and out["total_cost_usd"] is None and "not in the data" in out["cost_note"]
    assert tracks.cooling_centers(rows, 2, 1.5, cost_per_center=250000)["total_cost_usd"] == 250000  # one center fits
    assert tracks.cooling_centers([tract("cool", -1.0)], 3, 1.5)["status"] == "error"


def test_planting_ranks_by_people_heat_and_poverty_and_never_claims_an_intervention():
    rows = [tract("big", 3.0, pop=6000, poverty=0.35), tract("rich", 3.0, pop=6000, poverty=0.02), tract("cool", -2.0, pop=9000)]
    out = tracks.planting_sites(rows, 5)
    assert [s["geo_id"] for s in out["sites"]] == ["big", "rich"]  # the cool tract has no excess heat
    assert all(s["intervention"] == "undetermined" for s in out["sites"])
    assert any("canopy" in x for x in out["limits"])


def test_equity_audit_compares_chosen_areas_with_the_city():
    city = [tract("a", 1, poverty=0.10, cars=0.05), tract("b", 1, poverty=0.10, cars=0.05), tract("c", 1, poverty=0.40, cars=0.30)]
    chosen = [city[2]]
    audit = tracks.equity_audit(chosen, city)
    rows = {r["measure"]: r for r in audit["rows"]}
    assert rows["Poverty rate"]["verdict"] == "above the city" and rows["Households without a car"]["verdict"] == "above the city"
    assert "reaches vulnerable areas" in audit["summary"]
    better = tracks.equity_audit([city[0]], city)
    assert "better off" in better["summary"]
    assert "Race" in audit["note"]


def test_model_jargon_is_grouped_into_plain_driver_names():
    from heat_planner import modeling

    raw = [{"feature": "lat_lon", "effect_f": -1.13}, {"feature": "lon_sq", "effect_f": -0.43}, {"feature": "poverty_rate", "effect_f": -0.36}, {"feature": "mystery", "effect_f": 0.1}]
    out = modeling.group_drivers(raw)
    assert out[0] == {"feature": "Location in the city", "effect_f": -1.56}
    assert {"feature": "Poverty rate", "effect_f": -0.36} in out and {"feature": "mystery", "effect_f": 0.1} in out
    assert not any("lat" in d["feature"] or "lon" in d["feature"] for d in out[:2])


def test_customer_facing_text_never_names_the_technology():
    import json

    from heat_planner import prompts

    shown = json.dumps(tracks.TRACKS).lower()
    for word in ("bigquery", "gemini", "argon", "offset_model", "llm", "vertex"):
        assert word not in shown, word
    assert "never mention the technology" in prompts.ROOT.lower()


def test_track_names_say_what_the_track_does():
    assert [tracks.TRACKS[k]["title"] for k in ("today", "budget", "trees")] == ["Respond Today", "Fund Cooling Centers", "Grow the Canopy"]
