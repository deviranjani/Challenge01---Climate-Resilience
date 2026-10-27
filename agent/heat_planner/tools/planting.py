"""Tool for the This-decade track: where tree planting or cool pavement should start."""

from typing import Any

from .. import tracks, tracts
from ._common import CAVEATS, SOURCES, clamp_int, safe_tool


@safe_tool
def rank_planting_sites(top_n: int = 5) -> dict[str, Any]:
    """This-decade track: rank Dallas areas for a tree-planting program.

    Ranks areas by excess heat, residents and poverty, and audits who the program reaches. It cannot say whether planting
    or cool pavement fits an area, because no canopy or pavement data is loaded.

    Args:
        top_n: How many areas to return, 1 to 15. Defaults to 5.

    Returns:
        A dict with status, the ranked areas with what drives their heat, the limits of the analysis and an equity audit.
    """
    top_n = clamp_int(top_n, 1, 15, "top_n")
    result = tracks.planting_sites(tracts.load_tracts(), top_n)
    return {**result, "sources": SOURCES, "caveats": CAVEATS} if result["status"] == "ok" else result
