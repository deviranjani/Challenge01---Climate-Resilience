from heat_planner import api, mapdata
from fastapi.testclient import TestClient


def tract(geo_id, offset, poverty=0.15, cars=0.1, age=35.0, pop=1000):
    return {"geo_id": geo_id, "lat": 32.7, "lon": -96.8, "offset_f": offset, "median_age": age,
            "poverty_rate": poverty, "no_vehicle_rate": cars, "total_pop": pop, "drivers": []}


def test_graph_links_each_tract_to_shared_category_nodes():
    g = mapdata.build_graph([tract("a", 2.0, poverty=0.30, cars=0.25, age=45), tract("b", 2.5, poverty=0.30, cars=0.25, age=45)])
    labels = {n["id"] for n in g["nodes"]}
    assert "PovertyLevel:High poverty" in labels and "HeatBand:Hotter than average" in labels
    assert sum(1 for n in g["nodes"] if n["label"] == "Tract") == 2
    # two tracts share one node per category, so 4 category nodes, not 8
    assert sum(1 for n in g["nodes"] if n["label"] != "Tract") == 4
    assert len(g["edges"]) == 8 and {e["type"] for e in g["edges"]} == {"IN_HEAT_BAND", "HAS_POVERTY", "HAS_CAR_ACCESS", "HAS_AGE"}


def test_graph_keeps_only_the_hottest_tracts():
    tracts = [tract(str(i), float(i)) for i in range(10)]
    g = mapdata.build_graph(tracts, limit=3)
    assert g["tracts_shown"] == 3 and g["tracts_total"] == 10
    offsets = sorted(n["offset_f"] for n in g["nodes"] if n["label"] == "Tract")
    assert offsets == [7.0, 8.0, 9.0]


def test_graph_skips_categories_for_missing_values():
    g = mapdata.build_graph([tract("a", 0.0, poverty=None, age=None)])
    assert not any(n["label"] in ("PovertyLevel", "AgeBand") for n in g["nodes"])


def test_map_endpoints_return_data_and_map_errors(monkeypatch):
    client = TestClient(api.app)
    monkeypatch.setattr(mapdata, "measured_points", lambda limit: {"points": [], "min_offset_f": 0, "max_offset_f": 1, "avg_temp_f": 100})
    assert client.get("/api/map/points?limit=10").status_code == 200
    assert client.get("/api/map/points?limit=0").status_code == 422
    from heat_planner.bq import ToolError

    def boom():
        raise ToolError("no model")

    monkeypatch.setattr(mapdata, "tract_predictions", boom)
    res = client.get("/api/map/tracts")
    assert res.status_code == 503 and "no model" in res.json()["detail"]
