"""Shared helpers: input validation and a decorator that turns failures into tool results."""

import functools
import logging
import math
from typing import Any, Callable

from ..bq import ToolError

logger = logging.getLogger(__name__)

CAVEATS = [
    "Offsets describe one afternoon's spatial pattern (NOAA Heat Watch). They are not a forecast.",
    "Predictions away from the roads volunteers drove are extrapolation and less certain.",
]


def safe_tool(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Never let an exception escape to the LLM; return a structured error instead."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except ToolError as exc:
            logger.warning("%s failed: %s", fn.__name__, exc)
            return {"status": "error", "message": str(exc)}
        except Exception as exc:
            logger.exception("%s crashed", fn.__name__)
            return {"status": "error", "message": f"Unexpected error in {fn.__name__}: {type(exc).__name__}"}

    return wrapper


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise ToolError("latitude and longitude must be numbers.") from exc
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ToolError("latitude and longitude must be finite numbers.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ToolError("latitude must be in [-90, 90] and longitude in [-180, 180].")
    return lat, lon


def clamp_int(value: Any, low: int, high: int, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{name} must be a whole number.") from exc
    if not low <= number <= high:
        raise ToolError(f"{name} must be between {low} and {high}.")
    return number
