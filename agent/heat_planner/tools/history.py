"""Station history: how often does the city cross a heat threshold, and is it getting worse?"""

from typing import Any

from google.cloud import bigquery

from ..bq import ToolError, run_query, table
from ..config import load_settings
from ._common import safe_tool


@safe_tool
def heat_frequency(threshold_f: float = 100.0) -> dict[str, Any]:
    """Count days per year when any nearby weather station reached a temperature.

    Answers "how often does this happen?" and "is it getting worse?". This is regional
    air temperature from weather stations, not street-level heat.

    Args:
        threshold_f: Temperature in Fahrenheit, between 80 and 130. Defaults to 100.

    Returns:
        A dict with status, days_per_year (list of {year, days}) and a simple trend note.
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
                   COUNT(DISTINCT observation_date) AS days
            FROM {table(settings, 'station_daily_temps')}
            WHERE max_temp_f >= @threshold
            GROUP BY year ORDER BY year""",
        [bigquery.ScalarQueryParameter("threshold", "FLOAT64", threshold)],
        settings,
    )
    series = [{"year": int(r["year"]), "days": int(r["days"])} for r in rows]
    if not series:
        return {"status": "ok", "threshold_f": threshold, "days_per_year": [],
                "trend": "No station reached that temperature in the loaded years."}
    first, last = series[0], series[-1]
    direction = "rose" if last["days"] > first["days"] else "fell" if last["days"] < first["days"] else "held steady"
    return {
        "status": "ok",
        "threshold_f": threshold,
        "days_per_year": series,
        "trend": f"Days at or above {threshold:g}F {direction} from {first['days']} in {first['year']} "
                 f"to {last['days']} in {last['year']} (years without any such day are not listed).",
    }
