"""Parameterized BigQuery SQL builders and ingress row parsers (Node 3)."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from agent.models import (
    AgentConfig,
    CandidateSite,
    CityBaseline,
    Coordinates,
    FeatureAttribution,
)


@dataclass(frozen=True)
class ParameterizedQuery:
    """Immutable parameterized SQL statement and named parameter bindings."""

    sql: str
    params: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.sql, str) or not self.sql.strip():
            raise ValueError("sql must be a non-empty string")
        if not isinstance(self.params, dict):
            raise ValueError("params must be a dict")


def build_explain_predict_tracts_query(
    config: AgentConfig,
    *,
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lon: float | None = None,
    max_lon: float | None = None,
    limit: int = 500,
) -> ParameterizedQuery:
    """Build parameterized ML.EXPLAIN_PREDICT SQL across candidate census tracts."""
    if not isinstance(config, AgentConfig):
        raise TypeError("config must be an AgentConfig instance")
    if limit <= 0 or limit > config.max_results:
        raise ValueError(f"limit must be in [1, {config.max_results}], got {limit}")

    model_fqn = f"`{config.project_id}.{config.dataset}.{config.model_name}`"
    tracts_fqn = f"`{config.project_id}.{config.dataset}.tract_demographics`"

    filters = ["total_pop > 0", "tract_lat IS NOT NULL", "tract_lon IS NOT NULL"]
    params: dict[str, Any] = {"limit": int(limit)}

    if min_lat is not None:
        filters.append("tract_lat >= @min_lat")
        params["min_lat"] = float(min_lat)
    if max_lat is not None:
        filters.append("tract_lat <= @max_lat")
        params["max_lat"] = float(max_lat)
    if min_lon is not None:
        filters.append("tract_lon >= @min_lon")
        params["min_lon"] = float(min_lon)
    if max_lon is not None:
        filters.append("tract_lon <= @max_lon")
        params["max_lon"] = float(max_lon)

    where_clause = " AND ".join(filters)
    sql = f"""
SELECT
  *
FROM ML.EXPLAIN_PREDICT(
  MODEL {model_fqn},
  (
    SELECT
      LPAD(CAST(geo_id AS STRING), 11, '0') AS geo_id,
      tract_lat AS latitude,
      tract_lon AS longitude,
      tract_lat,
      tract_lon,
      COALESCE(total_pop, 0) AS total_pop,
      COALESCE(median_age, 35.0) AS median_age,
      COALESCE(median_income, 50000.0) AS median_income,
      COALESCE(housing_units, 0) AS housing_units,
      COALESCE(median_year_structure_built, 1980) AS median_year_structure_built,
      COALESCE(no_cars, 0) AS no_cars,
      COALESCE(households, 0) AS households,
      COALESCE(poverty_rate, 0.0) AS poverty_rate,
      COALESCE(no_vehicle_rate, 0.0) AS no_vehicle_rate
    FROM {tracts_fqn}
    WHERE {where_clause}
    LIMIT @limit
  ),
  STRUCT(3 AS top_k_features)
)
""".strip()
    return ParameterizedQuery(sql=sql, params=params)


def build_explain_point_query(
    config: AgentConfig,
    target: Coordinates,
) -> ParameterizedQuery:
    """Build parameterized ML.EXPLAIN_PREDICT SQL for an arbitrary unmeasured coordinate."""
    if not isinstance(config, AgentConfig):
        raise TypeError("config must be an AgentConfig instance")
    if not isinstance(target, Coordinates):
        raise TypeError("target must be a Coordinates instance")

    model_fqn = f"`{config.project_id}.{config.dataset}.{config.model_name}`"
    tracts_fqn = f"`{config.project_id}.{config.dataset}.tract_demographics`"

    sql = f"""
SELECT
  *
FROM ML.EXPLAIN_PREDICT(
  MODEL {model_fqn},
  (
    SELECT
      LPAD(CAST(geo_id AS STRING), 11, '0') AS geo_id,
      @target_lat AS latitude,
      @target_lon AS longitude,
      @target_lat AS tract_lat,
      @target_lon AS tract_lon,
      COALESCE(total_pop, 0) AS total_pop,
      COALESCE(median_age, 35.0) AS median_age,
      COALESCE(median_income, 50000.0) AS median_income,
      COALESCE(housing_units, 0) AS housing_units,
      COALESCE(median_year_structure_built, 1980) AS median_year_structure_built,
      COALESCE(no_cars, 0) AS no_cars,
      COALESCE(households, 0) AS households,
      COALESCE(poverty_rate, 0.0) AS poverty_rate,
      COALESCE(no_vehicle_rate, 0.0) AS no_vehicle_rate
    FROM {tracts_fqn}
    WHERE tract_lat IS NOT NULL AND tract_lon IS NOT NULL
    ORDER BY ST_DISTANCE(
      ST_GEOGPOINT(tract_lon, tract_lat),
      ST_GEOGPOINT(@target_lon, @target_lat)
    ) ASC
    LIMIT 1
  ),
  STRUCT(3 AS top_k_features)
)
""".strip()
    return ParameterizedQuery(
        sql=sql,
        params={"target_lat": target.latitude, "target_lon": target.longitude},
    )


def build_city_baseline_query(config: AgentConfig) -> ParameterizedQuery:
    """Build SQL query for city-wide tract_demographics baseline metrics."""
    if not isinstance(config, AgentConfig):
        raise TypeError("config must be an AgentConfig instance")

    tracts_fqn = f"`{config.project_id}.{config.dataset}.tract_demographics`"
    sql = f"""
SELECT
  COUNT(*) AS tract_count,
  AVG(poverty_rate) AS avg_poverty_rate,
  AVG(no_vehicle_rate) AS avg_no_vehicle_rate,
  AVG(median_age) AS avg_median_age,
  AVG(median_income) AS avg_median_income
FROM {tracts_fqn}
WHERE total_pop > 0
""".strip()
    return ParameterizedQuery(sql=sql, params={})


def build_station_frequency_query(
    config: AgentConfig,
    threshold_f: float = 95.0,
) -> ParameterizedQuery:
    """Build parameterized SQL query for 7-year GHCN station heat frequency."""
    if not isinstance(config, AgentConfig):
        raise TypeError("config must be an AgentConfig instance")
    if not math.isfinite(threshold_f) or not (50.0 <= threshold_f <= 135.0):
        raise ValueError(f"threshold_f must be in [50, 135], got {threshold_f}")

    stations_fqn = f"`{config.project_id}.{config.dataset}.station_daily_temps`"
    sql = f"""
WITH station_year AS (
  SELECT
    EXTRACT(YEAR FROM observation_date) AS obs_year,
    station_id,
    COUNTIF(max_temp_f >= @threshold_f) AS days_at_or_above_threshold,
    MAX(max_temp_f) AS peak_temp_f
  FROM {stations_fqn}
  GROUP BY obs_year, station_id
)
SELECT
  obs_year,
  ROUND(AVG(days_at_or_above_threshold), 1) AS avg_hot_days_per_station,
  ROUND(MAX(peak_temp_f), 1) AS max_recorded_temp_f
FROM station_year
GROUP BY obs_year
ORDER BY obs_year ASC
""".strip()
    return ParameterizedQuery(sql=sql, params={"threshold_f": float(threshold_f)})


def _extract_predicted_offset(row: Mapping[str, Any], predicted_label_col: str) -> float:
    """Resolve the predicted offset column from ML.EXPLAIN_PREDICT output."""
    if predicted_label_col in row and row[predicted_label_col] is not None:
        return float(row[predicted_label_col])
    for key, val in row.items():
        if key.startswith("predicted_") and val is not None:
            return float(val)
    raise KeyError(f"Predicted label column '{predicted_label_col}' not found in row: {list(row.keys())}")


def parse_candidate_site_row(
    row: Mapping[str, Any],
    predicted_label_col: str = "predicted_degrees_above_city_average",
) -> CandidateSite:
    """Parse a raw BigQuery ML.EXPLAIN_PREDICT row into an immutable CandidateSite."""
    if not isinstance(row, Mapping):
        raise TypeError("row must be a mapping")
    if not predicted_label_col.strip():
        raise ValueError("predicted_label_col must be non-empty")

    raw_attrs = row.get("top_feature_attributions") or ()
    attributions = tuple(
        FeatureAttribution(
            feature=str(item["feature"]),
            attribution=float(item["attribution"]),
        )
        for item in raw_attrs
        if isinstance(item, Mapping) and item.get("feature") and item.get("attribution") is not None
    )

    lat = float(row.get("latitude") if row.get("latitude") is not None else row["tract_lat"])
    lon = float(row.get("longitude") if row.get("longitude") is not None else row["tract_lon"])

    return CandidateSite(
        geo_id=str(row["geo_id"]).zfill(11),
        coordinates=Coordinates(latitude=lat, longitude=lon),
        predicted_offset_f=_extract_predicted_offset(row, predicted_label_col),
        total_pop=max(0, int(float(row.get("total_pop") or 0))),
        median_age=float(row.get("median_age") or 35.0),
        median_income=float(row.get("median_income") or 50000.0),
        housing_units=max(0, int(float(row.get("housing_units") or 0))),
        median_year_structure_built=int(float(row.get("median_year_structure_built") or 1980)),
        poverty_rate=min(1.0, max(0.0, float(row.get("poverty_rate") or 0.0))),
        no_vehicle_rate=min(1.0, max(0.0, float(row.get("no_vehicle_rate") or 0.0))),
        attributions=attributions,
    )


def parse_city_baseline_row(row: Mapping[str, Any], city: str) -> CityBaseline:
    """Parse a raw BigQuery aggregation row into an immutable CityBaseline."""
    if not isinstance(row, Mapping):
        raise TypeError("row must be a mapping")
    if not city.strip():
        raise ValueError("city must be non-empty")

    return CityBaseline(
        city=city.strip(),
        tract_count=int(row["tract_count"]),
        avg_poverty_rate=min(1.0, max(0.0, float(row["avg_poverty_rate"]))),
        avg_no_vehicle_rate=min(1.0, max(0.0, float(row["avg_no_vehicle_rate"]))),
        avg_median_age=float(row["avg_median_age"]),
        avg_median_income=float(row["avg_median_income"]),
    )
