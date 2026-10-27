import datetime

import pytest

from heat_planner.bq import ToolError
from heat_planner.tools import community, history, prediction
from heat_planner.tools._common import clamp_int, safe_tool, validate_coordinates

BOX = {"lat_min": 32.70, "lat_max": 32.80, "lon_min": -96.80, "lon_max": -96.70}


def fake_runner(*responses):
    """Return a run_query stand-in that yields each response in turn and records the SQL."""
    calls = []
    queue = list(responses)

    def run(sql, params=(), settings=None, max_rows=None):
        calls.append((sql, list(params)))
        return queue.pop(0)

    run.calls = calls
    return run


def test_validate_coordinates_rejects_bad_input():
    with pytest.raises(ToolError):
        validate_coordinates("abc", 1)
    with pytest.raises(ToolError):
        validate_coordinates(91, 0)
    with pytest.raises(ToolError):
        validate_coordinates(float("nan"), 0)
    assert validate_coordinates("32.7", "-96.8") == (32.7, -96.8)


def test_clamp_int_bounds():
    assert clamp_int(5, 1, 10, "n") == 5
    with pytest.raises(ToolError):
        clamp_int(0, 1, 10, "n")


def test_safe_tool_turns_exceptions_into_errors():
    @safe_tool
    def boom():
        raise RuntimeError("secret detail")

    result = boom()
    assert result["status"] == "error"
    assert "secret detail" not in result["message"]


def test_predict_out_of_coverage_does_not_call_model(monkeypatch):
    run = fake_runner([BOX])
    monkeypatch.setattr(prediction, "run_query", run)
    result = prediction.predict_heat_offset(40.0, -74.0)
    assert result["status"] == "out_of_coverage"
    assert len(run.calls) == 1  # only the coverage query, never ML.EXPLAIN_PREDICT


def test_predict_ok_returns_sorted_drivers_and_uses_parameters(monkeypatch):
    row = {
        "predicted_offset_f": 3.14159,
        "top_feature_attributions": [
            {"feature": "poverty_rate", "attribution": 0.2},
            {"feature": "dist_center_km", "attribution": -1.5},
        ],
        "median_age": 33.0, "poverty_rate": 0.2, "no_vehicle_rate": 0.1, "total_pop": 4000,
    }
    run = fake_runner([BOX], [row])
    monkeypatch.setattr(prediction, "run_query", run)
    result = prediction.predict_heat_offset(32.75, -96.75)
    assert result["status"] == "ok"
    assert result["predicted_offset_f"] == 3.14
    assert result["drivers"][0] == {"feature": "dist_center_km", "effect_f": -1.5}
    sql, params = run.calls[1]
    assert "ML.EXPLAIN_PREDICT" in sql and "32.75" not in sql  # values travel as parameters
    assert {p.name for p in params} == {"lat", "lon"}


def test_predict_handles_empty_model_result(monkeypatch):
    monkeypatch.setattr(prediction, "run_query", fake_runner([BOX], []))
    assert prediction.predict_heat_offset(32.75, -96.75)["status"] == "error"


def test_score_sites_ranks_hot_and_vulnerable_first():
    rows = [
        {"geo_id": "a", "predicted_offset_f": 1.0, "no_vehicle_rate": 0.05, "median_age": 30},
        {"geo_id": "b", "predicted_offset_f": 4.0, "no_vehicle_rate": 0.30, "median_age": 50},
        {"geo_id": "c", "predicted_offset_f": 2.0, "no_vehicle_rate": 0.10, "median_age": 35},
        {"geo_id": "skip", "predicted_offset_f": None, "no_vehicle_rate": 0.9, "median_age": 80},
    ]
    ranked = prediction.score_sites(rows, (0.5, 0.3, 0.2))
    assert [r["geo_id"] for r in ranked] == ["b", "c", "a"]


def test_rank_response_sites_validates_top_n():
    assert prediction.rank_response_sites(0)["status"] == "error"
    assert prediction.rank_response_sites(26)["status"] == "error"


def test_rank_response_sites_limits_results(monkeypatch):
    rows = [
        {"geo_id": str(i), "latitude": 1, "longitude": 1, "predicted_offset_f": float(i),
         "no_vehicle_rate": 0.1 * i, "median_age": 30 + i, "total_pop": 100,
         "top_feature_attributions": []}
        for i in range(6)
    ]
    monkeypatch.setattr(prediction, "run_query", fake_runner(rows))
    monkeypatch.setattr(prediction, "_within_coverage", lambda lat, lon: True)
    result = prediction.rank_response_sites(3)
    assert result["status"] == "ok" and len(result["sites"]) == 3
    assert result["sites"][0]["geo_id"] == "5"


def test_heat_frequency_validates_input():
    assert history.heat_frequency(10)["status"] == "error"
    assert history.heat_frequency("hot")["status"] == "error"


def test_heat_frequency_reports_every_year_and_a_summary(monkeypatch):
    rows = [{"year": y, "days": d, "last_day": datetime.date(y, 12, 31)}
            for y, d in zip(range(2019, 2026), [34, 27, 21, 65, 65, 40, 34])]
    monkeypatch.setattr(history, "run_query", fake_runner(rows))
    result = history.heat_frequency(100)
    assert result["status"] == "ok" and len(result["days_per_year"]) == 7
    assert result["peak_year"] in (2022, 2023) and result["peak_days"] == 65
    assert "Peak" in result["trend"]


def test_trend_is_not_just_first_versus_last_year():
    # The real Dallas pattern: first 34, last 14, but peaks of 65 in between. The old logic said "fell".
    series = [{"year": y, "days": d} for y, d in zip(range(2019, 2026), [34, 27, 21, 65, 65, 40, 14])]
    out = history.summarize_trend(series, 100.0, datetime.date(2025, 12, 31))
    assert out["direction"] == "no_clear_trend"
    assert "fell" not in out["summary"] and "No clear trend" in out["summary"]


def test_trend_detects_a_steady_rise_and_fall():
    rising = [{"year": 2015 + i, "days": 10 + 5 * i} for i in range(8)]
    falling = [{"year": 2015 + i, "days": 50 - 5 * i} for i in range(8)]
    up = history.summarize_trend(rising, 100.0)
    down = history.summarize_trend(falling, 100.0)
    assert up["direction"] == "rising" and up["slope_days_per_year"] == 5.0
    assert down["direction"] == "falling" and down["slope_days_per_year"] == -5.0


def test_partial_last_year_is_left_out_of_the_trend():
    # A summer that stops in June would look like a collapse if it were counted.
    series = [{"year": 2018 + i, "days": 20 + 3 * i} for i in range(7)] + [{"year": 2025, "days": 2}]
    out = history.summarize_trend(series, 100.0, datetime.date(2025, 6, 10))
    assert out["partial_last_year"] is True
    assert out["direction"] == "rising"


def test_too_few_years_says_so():
    out = history.summarize_trend([{"year": 2024, "days": 5}, {"year": 2025, "days": 9}], 100.0)
    assert out["direction"] == "insufficient_data" and "too few" in out["summary"]


def test_years_with_no_hot_days_are_kept_as_zero(monkeypatch):
    rows = [{"year": 2019, "days": 0, "last_day": datetime.date(2019, 12, 31)}]
    monkeypatch.setattr(history, "run_query", fake_runner(rows))
    assert history.heat_frequency(120)["days_per_year"] == [{"year": 2019, "days": 0}]


def test_community_profile_handles_no_tracts(monkeypatch):
    monkeypatch.setattr(community, "run_query", fake_runner([{"tracts": 0}]))
    assert community.community_profile(32.7, -96.8)["status"] == "error"


def test_community_profile_ok(monkeypatch):
    row = {"tracts": 4, "people": 12000, "median_age": 33.456, "poverty_rate": 0.1234, "no_vehicle_rate": None}
    monkeypatch.setattr(community, "run_query", fake_runner([row]))
    result = community.community_profile(32.7, -96.8, 3)
    assert result["status"] == "ok"
    assert result["median_age"] == 33.5 and result["no_vehicle_rate"] is None


def test_tracts_outside_measured_area_are_not_scored(monkeypatch):
    rows = [
        {"geo_id": "in", "latitude": 32.75, "longitude": -96.75, "predicted_offset_f": 2.0,
         "no_vehicle_rate": 0.1, "median_age": 30, "top_feature_attributions": []},
        {"geo_id": "far", "latitude": 33.04, "longitude": -97.01, "predicted_offset_f": 22.7,
         "no_vehicle_rate": 0.1, "median_age": 30, "top_feature_attributions": []},
    ]
    monkeypatch.setattr(prediction, "run_query", fake_runner(rows))
    monkeypatch.setattr(prediction, "_within_coverage", lambda lat, lon: lat < 33)
    assert [r["geo_id"] for r in prediction.predict_all_tracts()] == ["in"]


def test_tract_query_asks_for_more_than_the_default_row_cap(monkeypatch):
    seen = {}

    def run(sql, params=(), settings=None, max_rows=None):
        seen["max_rows"] = max_rows
        return []

    monkeypatch.setattr(prediction, "run_query", run)
    prediction.predict_all_tracts()
    assert seen["max_rows"] and seen["max_rows"] > 500  # 559 tracts were silently cut to 500 before
