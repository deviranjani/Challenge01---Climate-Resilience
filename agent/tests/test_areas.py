import pytest

from heat_planner import areas
from heat_planner.bq import ToolError


def tract(geo_id, lat, lon, nb=None, zip_code="75211", pop=1000):
    label = areas.display_label(nb, zip_code, "Dallas", geo_id)
    return {"geo_id": geo_id, "lat": lat, "lon": lon, "neighbourhood": nb, "zip": zip_code, "city": "Dallas", "total_pop": pop, "area": label}


TRACTS = [tract("1", 32.75, -96.87, "Oak Cliff"), tract("2", 32.74, -96.86, "Oak Cliff", pop=2000),
          tract("3", 32.77, -96.76, "South Dallas", "75215"), tract("4", 32.72, -96.70, None, "75217")]


def test_labels_prefer_the_neighbourhood_then_zip_then_the_tract():
    assert areas.display_label("Oak Cliff", "75211", "Dallas", "x") == "Oak Cliff · 75211"
    assert areas.display_label(None, "75217", "Dallas", "x") == "ZIP 75217 · Dallas"
    assert areas.display_label(None, None, None, "48113002200") == "Tract 002200"


def test_a_neighbourhood_name_matches_without_calling_google(monkeypatch):
    monkeypatch.setattr(areas, "search_place", lambda *a: pytest.fail("should not call Places for a name Google already gave us"))
    out = areas.resolve_area("the Oak Cliff area", TRACTS)
    assert out["status"] == "ok" and out["label"] == "Oak Cliff" and out["tract_count"] == 2 and out["source"] == "Google Maps"


def test_a_zip_code_resolves_from_bigquery_data():
    for text in ("75215", "zip 75215", "ZIP code 75215"):
        out = areas.resolve_area(text, TRACTS)
        assert out["status"] == "ok" and out["kind"] == "zip" and [t["geo_id"] for t in out["tracts"]] == ["3"] and out["source"] == "BigQuery"


def test_an_unknown_name_uses_places_bounds_then_filters_to_measured_tracts(monkeypatch):
    place = {"displayName": {"text": "Fair Park"}, "types": ["park", "point_of_interest"], "location": {"latitude": 32.7745, "longitude": -96.7640}}
    monkeypatch.setattr(areas, "search_place", lambda query, near: place)
    out = areas.resolve_area("Fair Park", TRACTS)
    assert out["status"] == "ok" and out["label"] == "Fair Park" and [t["geo_id"] for t in out["tracts"]] == ["3"]  # a point place: within 1.5 km


def test_a_neighbourhood_place_uses_its_map_bounds(monkeypatch):
    place = {"displayName": {"text": "Pleasant Grove"}, "types": ["neighborhood", "political"], "location": {"latitude": 32.72, "longitude": -96.70},
             "viewport": {"low": {"latitude": 32.70, "longitude": -96.72}, "high": {"latitude": 32.74, "longitude": -96.66}}}
    monkeypatch.setattr(areas, "search_place", lambda query, near: place)
    out = areas.resolve_area("Pleasant Grove", TRACTS)
    assert [t["geo_id"] for t in out["tracts"]] == ["4"]


def test_a_place_outside_the_measured_area_says_so_and_suggests_real_ones(monkeypatch):
    far = {"displayName": {"text": "Plano"}, "types": ["locality"], "location": {"latitude": 33.02, "longitude": -96.70},
           "viewport": {"low": {"latitude": 32.95, "longitude": -96.80}, "high": {"latitude": 33.10, "longitude": -96.60}}}
    monkeypatch.setattr(areas, "search_place", lambda query, near: far)
    out = areas.resolve_area("Plano", TRACTS)
    assert out["status"] == "not_found" and "Oak Cliff" in out["suggestions"] and "No measured heat data" in out["message"]


def test_empty_input_asks_which_area():
    out = areas.resolve_area("  ", TRACTS)
    assert out["status"] == "not_found" and out["suggestions"]


def test_known_areas_are_ranked_by_population_and_skip_unnamed_tracts():
    names = areas.known_areas(TRACTS)
    assert [n["name"] for n in names] == ["Oak Cliff", "South Dallas"] and names[0]["people"] == 3000


def test_haversine_is_about_right():
    assert areas.haversine_km((32.78, -96.80), (32.78, -96.80)) == 0
    assert 0.9 < areas.haversine_km((32.78, -96.80), (32.78, -96.79)) < 1.0  # 0.01 degree of longitude at this latitude is about 0.94 km


def test_a_missing_places_service_becomes_a_tool_error(monkeypatch):
    class Boom:
        def post(self, *a, **k):
            raise RuntimeError("down")

    monkeypatch.setattr(areas, "_session", lambda: Boom())
    with pytest.raises(ToolError, match="unavailable"):
        areas.search_place("x", (32.7, -96.8))
