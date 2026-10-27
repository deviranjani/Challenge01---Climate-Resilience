"""Station history: how often does the city cross a heat threshold, and is it getting worse?"""

import datetime
from typing import Any

from google.cloud import bigquery

from ..bq import ToolError, run_query, table
from ..config import load_settings
from ._common import safe_tool

MIN_YEARS_FOR_TREND = 5
MIN_R_SQUARED = 0.3        # below this the line explains too little of the year-to-year swing to call a trend
MIN_SLOPE_DAYS_PER_YEAR = 0.5
PARTIAL_YEAR_BEFORE = (10, 1)  # a last year whose data ends before Oct 1 is treated as incomplete


def _fit_line(years: list[int], days: list[int]) -> tuple[float, float]:
    """Least-squares slope (days per year) and R squared."""
    n = len(years)
    mean_x, mean_y = sum(years) / n, sum(days) / n
    sxx = sum((x - mean_x) ** 2 for x in years)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(years, days))
    syy = sum((y - mean_y) ** 2 for y in days)
    if sxx == 0 or syy == 0:
        return 0.0, 0.0
    return sxy / sxx, (sxy * sxy) / (sxx * syy)


def summarize_trend(series: list[dict[str, int]], threshold: float, last_day: Any = None) -> dict[str, Any]:
    """Describe the whole series, not just its two ends. Pure function, so it is easy to test.

    Years with no qualifying day must be present with days == 0. A final year whose data stops early
    is shown but left out of the trend, because a partial summer would fake a decline.
    """
    shown = f"{threshold:g}F"
    peak = max(series, key=lambda s: s["days"])
    average = sum(s["days"] for s in series) / len(series)
    parts = [f"Peak: {peak['days']} days in {peak['year']}. Average: {average:.0f} days a year."]

    used = series
    partial = (
        isinstance(last_day, datetime.date)
        and last_day.year == series[-1]["year"]
        and (last_day.month, last_day.day) < PARTIAL_YEAR_BEFORE
    )
    if partial:
        used = series[:-1]
        parts.append(f"{series[-1]['year']} data ends {last_day:%b %d}, so it is left out of the trend.")

    if len(used) < MIN_YEARS_FOR_TREND:
        parts.append(f"Only {len(used)} complete years of station data, too few to call a trend.")
        direction, slope = "insufficient_data", None
    else:
        slope, r2 = _fit_line([s["year"] for s in used], [s["days"] for s in used])
        if r2 >= MIN_R_SQUARED and abs(slope) >= MIN_SLOPE_DAYS_PER_YEAR:
            direction = "rising" if slope > 0 else "falling"
            parts.append(f"Days at or above {shown} are {direction} by about {abs(slope):.1f} days a year (fit R2 {r2:.2f}).")
        else:
            direction = "no_clear_trend"
            parts.append(f"No clear trend: the years swing too much (fit R2 {r2:.2f}) to say it is rising or falling.")
    return {"direction": direction, "slope_days_per_year": None if slope is None else round(slope, 2),
            "peak_year": peak["year"], "peak_days": peak["days"], "average_days": round(average, 1),
            "partial_last_year": partial, "summary": " ".join(parts)}


@safe_tool
def heat_frequency(threshold_f: float = 100.0) -> dict[str, Any]:
    """Count days per year when any nearby weather station reached a temperature.

    Answers "how often does this happen?" and "is it getting worse?". This is regional
    air temperature from weather stations, not street-level heat.

    Args:
        threshold_f: Temperature in Fahrenheit, between 80 and 130. Defaults to 100.

    Returns:
        A dict with status, days_per_year (every year in the data, zero included), a trend
        direction ("rising", "falling", "no_clear_trend" or "insufficient_data") and a plain summary.
    """
    try:
        threshold = float(threshold_f)
    except (TypeError, ValueError) as exc:
        raise ToolError("threshold_f must be a number.") from exc
    if not 80 <= threshold <= 130:
        raise ToolError("threshold_f must be between 80 and 130.")

    settings = load_settings()
    rows = run_query(
        f"""SELECT EXTRACT(YEAR FROM observation_date) AS year,
                   COUNT(DISTINCT IF(max_temp_f >= @threshold, observation_date, NULL)) AS days,
                   MAX(observation_date) AS last_day
            FROM {table(settings, 'station_daily_temps')}
            GROUP BY year ORDER BY year""",
        [bigquery.ScalarQueryParameter("threshold", "FLOAT64", threshold)],
        settings,
    )
    if not rows:
        raise ToolError("No station history is loaded.")
    series = [{"year": int(r["year"]), "days": int(r["days"])} for r in rows]
    result = summarize_trend(series, threshold, rows[-1].get("last_day"))
    return {"status": "ok", "threshold_f": threshold, "days_per_year": series, "trend": result["summary"],
            **{k: v for k, v in result.items() if k != "summary"}}
