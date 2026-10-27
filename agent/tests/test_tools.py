import datetime

import pytest

from heat_planner.bq import ToolError
from heat_planner.tools import history
from heat_planner.tools._common import clamp_int, safe_tool, validate_coordinates



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
