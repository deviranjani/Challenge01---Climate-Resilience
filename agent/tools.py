"""Imperative shell: BigQuery query execution and ADK function tools (Node 4)."""

from __future__ import annotations

from dataclasses import asdict
import os
from typing import Any, Callable, Mapping, Sequence

from agent.models import (
    AgentConfig,
    Coordinates,
    DispatchStop,
    InterventionType,
    parse_agent_config,
)
from agent.queries import (
    ParameterizedQuery,
    build_city_baseline_query,
    build_explain_point_query,
    build_explain_predict_tracts_query,
    build_station_frequency_query,
    parse_candidate_site_row,
    parse_city_baseline_row,
)
from agent.scoring import (
    audit_outcome_equity,
    format_feature_attributions,
    rank_dispatch_stops,
    score_hydration_truck,
    score_wellness_check,
)

QueryRunner = Callable[[ParameterizedQuery, float, int], Sequence[Mapping[str, Any]]]


def _infer_bq_param_type(value: Any) -> str:
    """Map a Python scalar value to its BigQuery parameter type name."""
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    return "STRING"


def execute_bigquery(
    query: ParameterizedQuery,
    timeout_sec: float,
    max_results: int,
    *,
    project_id: str | None = None,
    location: str = "US",
) -> Sequence[Mapping[str, Any]]:
    """Execute a parameterized query against BigQuery with bounded timeout and row limit."""
    if timeout_sec <= 0 or max_results <= 0:
        raise ValueError("timeout_sec and max_results must be positive")

    from google.cloud import bigquery  # Lazy import so unit tests run without GCP SDK installed

    client = bigquery.Client(project=project_id, location=location)
    bq_params = [
        bigquery.ScalarQueryParameter(name, _infer_bq_param_type(val), val)
        for name, val in query.params.items()
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=bq_params)
    job = client.query(query.sql, job_config=job_config, timeout=timeout_sec)
    rows = job.result(timeout=timeout_sec, max_results=max_results)
    return [dict(row.items()) for row in rows]


def _serialize_stop(stop: DispatchStop) -> dict[str, Any]:
    """Convert a DispatchStop domain object into a JSON-serializable dictionary."""
    return {
        "rank": stop.rank,
        "intervention": stop.intervention.value,
        "geo_id": stop.site.geo_id,
        "latitude": stop.site.coordinates.latitude,
        "longitude": stop.site.coordinates.longitude,
        "predicted_offset_f": stop.site.predicted_offset_f,
        "expected_local_temp_f": stop.expected_local_temp_f,
        "priority_score": stop.priority_score,
        "primary_drivers": list(stop.primary_drivers),
        "demographics": {
            "total_pop": stop.site.total_pop,
            "median_age": stop.site.median_age,
            "median_income": stop.site.median_income,
            "housing_units": stop.site.housing_units,
            "median_year_structure_built": stop.site.median_year_structure_built,
            "poverty_rate": stop.site.poverty_rate,
            "no_vehicle_rate": stop.site.no_vehicle_rate,
        },
        "operational_rationale": stop.operational_rationale,
    }


class ClimateToolService:
    """Service coordinating BigQuery ML.EXPLAIN_PREDICT queries with the pure scoring core."""

    def __init__(self, config: AgentConfig, runner: QueryRunner | None = None) -> None:
        if not isinstance(config, AgentConfig):
            raise TypeError("config must be an AgentConfig instance")
        self._config = config
        self._runner: QueryRunner = runner or (
            lambda q, timeout, max_res: execute_bigquery(
                q,
                timeout,
                max_res,
                project_id=config.project_id,
                location=config.location,
            )
        )

    def _run_dispatch_plan(
        self,
        intervention: InterventionType,
        forecast_high_f: float,
        top_k: int,
        min_lat: float | None,
        max_lat: float | None,
        min_lon: float | None,
        max_lon: float | None,
    ) -> dict[str, Any]:
        tracts_q = build_explain_predict_tracts_query(
            self._config,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            limit=self._config.max_results,
        )
        raw_candidates = self._runner(
            tracts_q, self._config.query_timeout_sec, self._config.max_results
        )
        if not raw_candidates:
            raise RuntimeError("No candidate census tracts returned from ML.EXPLAIN_PREDICT.")

        candidates = tuple(
            parse_candidate_site_row(r, self._config.predicted_label_col) for r in raw_candidates
        )
        stops = rank_dispatch_stops(
            candidates,
            intervention=intervention,
            forecast_high_f=forecast_high_f,
            top_k=top_k,
        )

        base_q = build_city_baseline_query(self._config)
        base_rows = self._runner(base_q, self._config.query_timeout_sec, 1)
        if not base_rows:
            raise RuntimeError("City baseline query returned no rows from tract_demographics.")

        baseline = parse_city_baseline_row(base_rows[0], city=self._config.target_city)
        audit = audit_outcome_equity(stops, baseline)

        return {
            "city": self._config.target_city,
            "intervention": intervention.value,
            "forecast_high_f": forecast_high_f,
            "stops": [_serialize_stop(s) for s in stops],
            "equity_audit": asdict(audit),
        }

    def recommend_hydration_trucks(
        self,
        forecast_high_f: float = 102.0,
        top_k: int = 5,
        min_lat: float | None = None,
        max_lat: float | None = None,
        min_lon: float | None = None,
        max_lon: float | None = None,
    ) -> dict[str, Any]:
        """Rank top Hydration Truck stops using BQML ML.EXPLAIN_PREDICT and transit-dependence metrics."""
        return self._run_dispatch_plan(
            InterventionType.HYDRATION_TRUCK,
            forecast_high_f=forecast_high_f,
            top_k=top_k,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
        )

    def recommend_wellness_checks(
        self,
        forecast_high_f: float = 102.0,
        top_k: int = 5,
        min_lat: float | None = None,
        max_lat: float | None = None,
        min_lon: float | None = None,
        max_lon: float | None = None,
    ) -> dict[str, Any]:
        """Rank top door-to-door Wellness Check zones using BQML ML.EXPLAIN_PREDICT and indoor isolation metrics."""
        return self._run_dispatch_plan(
            InterventionType.WELLNESS_CHECK,
            forecast_high_f=forecast_high_f,
            top_k=top_k,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
        )

    def explain_location_heat_risk(
        self,
        latitude: float,
        longitude: float,
        forecast_high_f: float = 102.0,
    ) -> dict[str, Any]:
        """Run BQML ML.EXPLAIN_PREDICT for an arbitrary coordinate and return attributions and dispatch scores."""
        target = Coordinates(latitude=latitude, longitude=longitude)
        q = build_explain_point_query(self._config, target)
        rows = self._runner(q, self._config.query_timeout_sec, 1)
        if not rows:
            raise RuntimeError(f"No prediction available for ({latitude}, {longitude}).")

        site = parse_candidate_site_row(rows[0], self._config.predicted_label_col)
        drivers = format_feature_attributions(site.attributions, top_n=3)
        return {
            "city": self._config.target_city,
            "geo_id": site.geo_id,
            "latitude": site.coordinates.latitude,
            "longitude": site.coordinates.longitude,
            "predicted_offset_f": site.predicted_offset_f,
            "expected_local_temp_f": round(forecast_high_f + site.predicted_offset_f, 1),
            "primary_drivers": list(drivers),
            "hydration_truck_score": score_hydration_truck(site),
            "wellness_check_score": score_wellness_check(site),
            "demographics": {
                "total_pop": site.total_pop,
                "median_age": site.median_age,
                "median_income": site.median_income,
                "housing_units": site.housing_units,
                "median_year_structure_built": site.median_year_structure_built,
                "poverty_rate": site.poverty_rate,
                "no_vehicle_rate": site.no_vehicle_rate,
            },
        }

    def get_heat_wave_frequency(self, threshold_f: float = 100.0) -> dict[str, Any]:
        """Query 7 years of NOAA GHCN station history for annual days at or above threshold_f."""
        q = build_station_frequency_query(self._config, threshold_f=threshold_f)
        rows = self._runner(q, self._config.query_timeout_sec, 50)
        return {
            "city": self._config.target_city,
            "threshold_f": threshold_f,
            "yearly_history": [dict(r) for r in rows],
        }


def build_adk_tool_functions(
    config: AgentConfig | None = None,
    runner: QueryRunner | None = None,
) -> tuple[Callable[..., dict[str, Any]], ...]:
    """Create bound function tools for Google ADK registration."""
    resolved_config = config or parse_agent_config(os.environ)
    service = ClimateToolService(config=resolved_config, runner=runner)

    def recommend_hydration_trucks(
        forecast_high_f: float = 102.0,
        top_k: int = 5,
        min_lat: float | None = None,
        max_lat: float | None = None,
        min_lon: float | None = None,
        max_lon: float | None = None,
    ) -> dict[str, Any]:
        """Recommend ranked mobile Hydration Truck stops for Today's heat emergency.

        Calls BigQuery ML.EXPLAIN_PREDICT to predict street-level heat offsets, ranks tracts by
        heat offset, carless household rate (no_vehicle_rate), poverty rate, and exposed population,
        and performs an automated Outcome Equity Audit against the city baseline.
        """
        return service.recommend_hydration_trucks(
            forecast_high_f=forecast_high_f,
            top_k=top_k,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
        )

    def recommend_wellness_checks(
        forecast_high_f: float = 102.0,
        top_k: int = 5,
        min_lat: float | None = None,
        max_lat: float | None = None,
        min_lon: float | None = None,
        max_lon: float | None = None,
    ) -> dict[str, Any]:
        """Recommend ranked door-to-door Wellness Check zones for Today's heat emergency.

        Calls BigQuery ML.EXPLAIN_PREDICT to predict street-level heat offsets, ranks tracts by
        heat offset, elderly residents (median_age), pre-AC housing age (median_year_structure_built),
        carless household rate (no_vehicle_rate), and poverty rate, and runs an Outcome Equity Audit.
        """
        return service.recommend_wellness_checks(
            forecast_high_f=forecast_high_f,
            top_k=top_k,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
        )

    def explain_location_heat_risk(
        latitude: float,
        longitude: float,
        forecast_high_f: float = 102.0,
    ) -> dict[str, Any]:
        """Predict heat offset and explain feature attributions for any coordinate via ML.EXPLAIN_PREDICT."""
        return service.explain_location_heat_risk(
            latitude=latitude,
            longitude=longitude,
            forecast_high_f=forecast_high_f,
        )

    def get_heat_wave_frequency(threshold_f: float = 100.0) -> dict[str, Any]:
        """Query 7 years of NOAA GHCN-Daily weather station history for days >= threshold_f."""
        return service.get_heat_wave_frequency(threshold_f=threshold_f)

    return (
        recommend_hydration_trucks,
        recommend_wellness_checks,
        explain_location_heat_risk,
        get_heat_wave_frequency,
    )
