"""Google ADK Agent definition for Dallas Urban Heat Resilience — Today Track."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from agent.models import AgentConfig, parse_agent_config
from agent.tools import QueryRunner, build_adk_tool_functions


def parse_dotenv_lines(lines: Iterable[str]) -> dict[str, str]:
    """Parse KEY=VALUE lines from a .env file without external dependencies."""
    if lines is None:
        raise ValueError("lines must not be None")
    parsed: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        clean_key = key.strip()
        clean_val = val.strip().strip("'").strip('"')
        if clean_key:
            parsed[clean_key] = clean_val
    return parsed


def _merged_env() -> Mapping[str, str]:
    """Merge .env file (if present in repo root or agent/) with process environment."""
    merged: dict[str, str] = {}
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (repo_root / ".env", Path(__file__).resolve().parent / ".env"):
        if candidate.is_file():
            merged.update(parse_dotenv_lines(candidate.read_text(encoding="utf-8").splitlines()))
    merged.update(os.environ)
    return merged


def build_system_instruction(city: str, default_forecast_high_f: float) -> str:
    """Construct the system prompt for the Today-track Emergency Management Heat Agent."""
    if not city.strip():
        raise ValueError("city must be non-empty")
    if default_forecast_high_f <= 0:
        raise ValueError("default_forecast_high_f must be positive")

    return f"""You are the Emergency Management Heat Response Assistant for the City of {city} (Track: ⚡ Today).
The forecast high is {default_forecast_high_f:.1f}°F. Your user is an emergency dispatcher or city planner making immediate operational decisions today:
1. **Where to send Mobile Hydration Trucks (`recommend_hydration_trucks`)**:
   - Targets exposed outdoor and transit-dependent corridors where people walk or wait without vehicles.
   - Prioritizes high BigQuery ML predicted heat offset (`predicted_offset_f`), high `no_vehicle_rate`, high `poverty_rate`, and large exposed population (`total_pop`).
2. **Where to send Door-to-Door Wellness Checks (`recommend_wellness_checks`)**:
   - Targets indoor, isolated residents who cannot self-evacuate during extreme heat.
   - Prioritizes high BigQuery ML predicted heat offset (`predicted_offset_f`), older residents (`median_age`), older housing stock (`median_year_structure_built`), high `no_vehicle_rate`, and high `poverty_rate`.
3. **Unmeasured Locations & Feature Attributions (`explain_location_heat_risk`)**:
   - Always call `ML.EXPLAIN_PREDICT` tools to predict the **heat offset** (degrees above the {city} average, not raw temperature) and add the forecast high to report expected street-level temperature.
   - Always cite the per-feature attributions returned by `ML.EXPLAIN_PREDICT` to explain *why* a location runs hotter.
4. **Historical Frequency (`get_heat_wave_frequency`)**:
   - Distinguish the single-day NOAA Heat Watch spatial snapshot (which tells us *where* within {city} it is hottest) from the 7-year NOAA GHCN-Daily station history (which tells us *how often* {city} crosses dangerous heat thresholds).
5. **Mandatory Outcome Equity Audit & Honest Limitations**:
   - Race is deliberately excluded from model inputs because physical built-environment and socioeconomic exposure variables are measured directly.
   - Every dispatch recommendation includes a post-hoc **Outcome Equity Audit** comparing recommended tracts' poverty rate, no-vehicle rate, median age, and median income against the {city} city-wide baseline. Always report those exact audit numbers.
   - Refuse requests for cities outside {city} or interventions not grounded in the loaded tables, and explicitly state data limitations (single-day traverse snapshot, straight-line tract centroids rather than turn-by-turn walk isochrones).
"""


def _load_mcp_tools(config: AgentConfig) -> list[Any]:
    """Load managed MCP Toolbox tools if MCP_TOOLBOX_URL is configured."""
    if not config.mcp_toolbox_url:
        return []
    try:
        from toolbox_core import ToolboxSyncClient  # type: ignore[import-not-found]

        client = ToolboxSyncClient(config.mcp_toolbox_url)
        return list(client.load_toolset(config.mcp_toolbox_toolset))
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load MCP Toolbox toolset '{config.mcp_toolbox_toolset}' "
            f"from {config.mcp_toolbox_url}: {exc}"
        ) from exc


def create_agent(
    config: AgentConfig | None = None,
    runner: QueryRunner | None = None,
) -> Any:
    """Create the Google ADK Agent instance wired with custom BQML tools and MCP Toolbox."""
    resolved_config = config or parse_agent_config(_merged_env())
    custom_tools = list(build_adk_tool_functions(config=resolved_config, runner=runner))
    mcp_tools = _load_mcp_tools(resolved_config)
    instruction = build_system_instruction(
        city=resolved_config.target_city,
        default_forecast_high_f=resolved_config.default_forecast_high_f,
    )

    from google.adk.agents import Agent  # type: ignore[import-not-found]

    return Agent(
        name="dallas_heat_today_agent",
        model=resolved_config.gemini_model,
        description=(
            f"Emergency Management Urban Heat Dispatch Agent for {resolved_config.target_city} "
            "(Hydration Trucks & Wellness Checks powered by BigQuery ML.EXPLAIN_PREDICT)."
        ),
        instruction=instruction,
        tools=custom_tools + mcp_tools,
    )


def _init_default_root_agent() -> Any:
    """Initialize ADK root_agent when environment and google-adk are present."""
    env = _merged_env()
    if not env.get("GOOGLE_CLOUD_PROJECT"):
        return None
    try:
        return create_agent(parse_agent_config(env))
    except ImportError:
        return None


root_agent = _init_default_root_agent()
