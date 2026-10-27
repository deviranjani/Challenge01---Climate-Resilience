"""Weather forecast from the US National Weather Service (public domain, no key).

The model predicts how much hotter a place is than the city average. The forecast supplies the "average":
expected temperature = forecast high + predicted offset.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .bq import ToolError
from .config import load_settings

logger = logging.getLogger(__name__)

NWS = "https://api.weather.gov"
CACHE_SECONDS = 900
TIMEOUT_S = 12
# Dallas city centre; the forecast grid cell is the same across the city for our purposes.
DEFAULT_POINT = (32.7767, -96.7970)

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": load_settings().nws_user_agent, "Accept": "application/geo+json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 (fixed https host)
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("NWS request failed: %s: %s", type(exc).__name__, exc)
        raise ToolError("The National Weather Service forecast is unavailable right now.") from exc


def parse_periods(properties: dict[str, Any], days: int = 7) -> list[dict[str, Any]]:
    """Turn NWS 12-hour periods into one entry per calendar day: the daytime high and the night low after it."""
    periods = properties.get("periods", [])
    out: list[dict[str, Any]] = []
    for i, p in enumerate(periods):
        if not p.get("isDaytime") or p.get("temperature") is None:
            continue
        night = periods[i + 1] if i + 1 < len(periods) and not periods[i + 1].get("isDaytime") else None
        rain = (p.get("probabilityOfPrecipitation") or {}).get("value")
        out.append({
            "date": str(p["startTime"])[:10],
            "name": p.get("name"),
            "high_f": int(p["temperature"]),
            "low_f": None if not night or night.get("temperature") is None else int(night["temperature"]),
            "summary": p.get("shortForecast"),
            "precip_pct": rain,
        })
    return out[:days]


def get_forecast(lat: float = DEFAULT_POINT[0], lon: float = DEFAULT_POINT[1]) -> dict[str, Any]:
    key = f"{lat:.3f},{lon:.3f}"
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    point = _get_json(f"{NWS}/points/{lat:.4f},{lon:.4f}")["properties"]
    props = _get_json(point["forecast"])["properties"]
    days = parse_periods(props)
    if not days:
        raise ToolError("The forecast had no daytime periods.")
    result = {"source": "National Weather Service (api.weather.gov)", "updated": props.get("updateTime"),
              "place": point.get("relativeLocation", {}).get("properties", {}).get("city"), "days": days}
    with _lock:
        _cache[key] = (time.monotonic(), result)
    return result
