import pytest
from fastapi.testclient import TestClient

from heat_planner import api, areas, proposal, tracts
from heat_planner.tools import community, planting, prediction, siting
from test_areas import TRACTS as AREA_TRACTS  # noqa: F401  (same fixtures style)


def tract(geo_id, offset, nb, zip_code="75211", pop=2000, poverty=0.2, cars=0.1, age=35.0, lat=32.75, lon=-96.80):
    return {"geo_id": geo_id, "lat": lat, "lon": lon, "offset_f": offset, "total_pop": pop, "poverty_rate": poverty, "no_vehicle_rate": cars, "median_age": age,
            "neighbourhood": nb, "zip": zip_code, "city": "Dallas", "area": areas.display_label(nb, zip_code, "Dallas", geo_id),
            "drivers": [{"feature": "lon_sq", "effect_f": offset}]}


DATA = [tract("1", 3.0, "Oak Cliff", poverty=0.35, cars=0.3, lat=32.75, lon=-96.87), tract("2", 1.0, "Oak Cliff", pop=4000, lat=32.74, lon=-96.86),
        tract("3", -1.0, "Lakewood", "75214", poverty=0.05, lat=32.80, lon=-96.75)]


@pytest.fixture(autouse=True)
def fake_tracts(monkeypatch):
    monkeypatch.setattr(tracts, "load_tracts", lambda: DATA)


def test_predict_heat_offset_takes_an_area_name_and_averages_by_population():
    out = prediction.predict_heat_offset("Oak Cliff")
    assert out["status"] == "ok" and out["area"] == "Oak Cliff" and out["tracts"] == 2 and out["people"] == 6000
    assert out["predicted_offset_f"] == pytest.approx((3.0 * 2000 + 1.0 * 4000) / 6000, abs=0.01)
    assert out["range_f"] == [1.0, 3.0] and out["drivers"][0]["feature"] == "lon_sq"
    assert "NOAA" in out["sources"] and "BigQuery" not in out["sources"]


def test_an_unknown_area_returns_suggestions_instead_of_guessing(monkeypatch):
    monkeypatch.setattr(areas, "search_place", lambda *a: None)
    out = prediction.predict_heat_offset("Atlantis")
    assert out["status"] == "not_found" and "Oak Cliff" in out["suggestions"]


def test_rank_response_sites_validates_and_names_areas():
    assert prediction.rank_response_sites("hydration", 0)["status"] == "error"
    out = prediction.rank_response_sites("wellness", 2)
    assert out["status"] == "ok" and out["focus_label"] == "Wellness checks" and len(out["sites"]) == 2
    assert out["sites"][0]["area"].startswith(("Oak Cliff", "Lakewood")) and out["audit"]["rows"]


def test_community_profile_compares_the_area_with_the_city():
    out = community.community_profile("Oak Cliff")
    assert out["status"] == "ok" and out["total_population"] == 6000
    assert out["city"]["poverty_rate"] is not None and out["poverty_rate"] > out["city"]["poverty_rate"]


def test_cooling_centers_tool_validates_and_adds_heat_days(monkeypatch):
    monkeypatch.setattr(siting, "heat_frequency", lambda t: {"status": "ok", "average_days": 38.0, "peak_year": 2022, "peak_days": 65, "trend": "No clear trend"})
    assert siting.recommend_cooling_centers(0)["status"] == "error"
    assert siting.recommend_cooling_centers(2, radius_km=99)["status"] == "error"
    out = siting.recommend_cooling_centers(2, 1.5, 100000)
    assert out["status"] == "ok" and out["heat_days"]["peak_year"] == 2022 and out["total_cost_usd"] == 100000 * out["count"]


def test_cooling_centers_tool_survives_missing_station_history(monkeypatch):
    monkeypatch.setattr(siting, "heat_frequency", lambda t: {"status": "error", "message": "no history"})
    assert siting.recommend_cooling_centers(1)["heat_days"] is None


def test_planting_tool_never_claims_which_intervention():
    out = planting.rank_planting_sites(2)
    assert out["status"] == "ok" and all(s["intervention"] == "undetermined" for s in out["sites"]) and out["limits"]


# ----------------------------------------------------------------------------------------------- API
@pytest.fixture()
def client():
    return TestClient(api.app)


def test_tracks_endpoint_gives_the_ui_its_problem_statements(client):
    d = client.get("/api/tracks").json()
    assert [t["id"] for t in d["tracks"]] == ["today", "budget", "trees"] and d["focus"]["hydration"] == "Hydration trucks"


def test_track_endpoints_return_decisions_from_the_tract_data(client, monkeypatch):
    monkeypatch.setattr(api, "heat_frequency", lambda t: {"status": "ok", "average_days": 38.0, "peak_year": 2022, "peak_days": 65, "trend": "t", "days_per_year": []})
    today = client.get("/api/today?focus=wellness&limit=2").json()
    assert today["focus"] == "wellness" and len(today["sites"]) == 2
    budget = client.get("/api/budget?count=2&radius_km=2&cost_per_center=50000").json()
    assert budget["count"] >= 1 and budget["heat_days"]["peak_year"] == 2022 and budget["total_cost_usd"] == 50000 * budget["count"]
    assert client.get("/api/trees?limit=2").json()["sites"][0]["intervention"] == "undetermined"
    assert client.get("/api/today?focus=nonsense").status_code == 422 and client.get("/api/budget?count=99").status_code == 422


def test_areas_endpoint_lists_named_areas(client):
    assert client.get("/api/areas").json()["areas"][0]["name"] == "Oak Cliff"


def test_the_public_api_does_not_disclose_models_or_internals(client):
    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/api/model-info").status_code == 404
    assert client.get("/api/docs").status_code == 404 and client.get("/api/openapi.json").status_code == 404


class FakeGenai:
    def __init__(self):
        self.prompt = None
        self.models = self

    def generate_content(self, model, contents, config):
        self.prompt = contents
        return type("R", (), {"text": "Recommendation: ..."})()


def test_proposal_is_drafted_only_from_the_figures(client, monkeypatch):
    fake = FakeGenai()
    monkeypatch.setattr(proposal, "make_client", lambda: fake)
    monkeypatch.setattr(api, "heat_frequency", lambda t: {"status": "ok", "average_days": 38.0, "peak_year": 2022, "peak_days": 65, "trend": "t"})
    res = client.post("/api/proposal", json={"track": "budget", "count": 2})
    assert res.status_code == 200 and res.json()["text"].startswith("Recommendation") and res.json()["track"] == "budget"
    assert "model" not in res.json()
    assert "Use ONLY the figures" in fake.prompt and "Oak Cliff" in fake.prompt and "city council" in fake.prompt
    assert "as a percentage" in fake.prompt
    assert client.post("/api/proposal", json={"track": "nope"}).status_code == 422


def test_proposal_failure_is_a_plain_503(client, monkeypatch):
    def boom():
        raise RuntimeError("quota")

    monkeypatch.setattr(proposal, "make_client", boom)
    res = client.post("/api/proposal", json={"track": "trees"})
    assert res.status_code == 503 and "quota" not in res.text
