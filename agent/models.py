"""Immutable domain models and ingress boundary parsers for Climate Resilience Agent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Mapping

_SQL_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,62}$")
_GEO_ID_RE = re.compile(r"^\d{11}$")
_PLACEHOLDER_PROJECTS = frozenset({"your-gcp-project-id", "your-project-id-here", "changeme"})

DEFAULT_FEATURE_COLUMNS: tuple[str, ...] = (
    "latitude",
    "longitude",
    "total_pop",
    "median_age",
    "median_income",
    "housing_units",
    "median_year_structure_built",
    "no_cars",
    "households",
    "poverty_rate",
    "no_vehicle_rate",
)


class InterventionType(str, Enum):
    """Emergency management Today-track intervention types."""

    HYDRATION_TRUCK = "hydration_truck"
    WELLNESS_CHECK = "wellness_check"


def validate_sql_identifier(raw: str, field_name: str, *, allow_hyphen: bool = False) -> str:
    """Parse and validate a BigQuery identifier to prevent SQL injection at boundaries."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Invalid SQL identifier for {field_name}: must be a non-empty string")
    cleaned = raw.strip()
    pattern = _PROJECT_ID_RE if allow_hyphen else _SQL_ID_RE
    if not pattern.match(cleaned):
        raise ValueError(f"Invalid SQL identifier for {field_name}: '{cleaned}'")
    return cleaned


@dataclass(frozen=True)
class Coordinates:
    """Geographic coordinates validated to physical WGS84 bounds."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.latitude) or not (-90.0 <= self.latitude <= 90.0):
            raise ValueError(f"latitude out of bounds [-90, 90]: {self.latitude}")
        if not math.isfinite(self.longitude) or not (-180.0 <= self.longitude <= 180.0):
            raise ValueError(f"longitude out of bounds [-180, 180]: {self.longitude}")


@dataclass(frozen=True)
class FeatureAttribution:
    """Single feature attribution returned by BigQuery ML.EXPLAIN_PREDICT."""

    feature: str
    attribution: float

    def __post_init__(self) -> None:
        if not isinstance(self.feature, str) or not self.feature.strip():
            raise ValueError("feature name must be a non-empty string")
        if not math.isfinite(self.attribution):
            raise ValueError(f"attribution must be finite: {self.attribution}")


@dataclass(frozen=True)
class CandidateSite:
    """A census tract / microclimate candidate with BQML prediction and ACS demographics."""

    geo_id: str
    coordinates: Coordinates
    predicted_offset_f: float
    total_pop: int
    median_age: float
    median_income: float
    housing_units: int
    median_year_structure_built: int
    poverty_rate: float
    no_vehicle_rate: float
    attributions: tuple[FeatureAttribution, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.geo_id, str) or not _GEO_ID_RE.match(self.geo_id):
            raise ValueError(f"geo_id must be an 11-digit FIPS string, got '{self.geo_id}'")
        if not math.isfinite(self.predicted_offset_f) or not (-40.0 <= self.predicted_offset_f <= 40.0):
            raise ValueError(f"predicted_offset_f out of physical bounds: {self.predicted_offset_f}")
        if self.total_pop < 0 or self.housing_units < 0:
            raise ValueError("total_pop and housing_units must be non-negative")
        if not (0.0 <= self.poverty_rate <= 1.0):
            raise ValueError(f"poverty_rate must be in [0, 1], got {self.poverty_rate}")
        if not (0.0 <= self.no_vehicle_rate <= 1.0):
            raise ValueError(f"no_vehicle_rate must be in [0, 1], got {self.no_vehicle_rate}")


@dataclass(frozen=True)
class DispatchStop:
    """A ranked emergency dispatch stop for a Hydration Truck or Wellness Check team."""

    rank: int
    intervention: InterventionType
    site: CandidateSite
    expected_local_temp_f: float
    priority_score: float
    primary_drivers: tuple[str, ...]
    operational_rationale: str

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError(f"rank must be >= 1, got {self.rank}")
        if not math.isfinite(self.expected_local_temp_f) or not math.isfinite(self.priority_score):
            raise ValueError("expected_local_temp_f and priority_score must be finite")
        if not self.operational_rationale.strip():
            raise ValueError("operational_rationale must be non-empty")


@dataclass(frozen=True)
class CityBaseline:
    """City-wide demographic baseline from tract_demographics for outcome equity auditing."""

    city: str
    tract_count: int
    avg_poverty_rate: float
    avg_no_vehicle_rate: float
    avg_median_age: float
    avg_median_income: float

    def __post_init__(self) -> None:
        if not self.city.strip():
            raise ValueError("city must be non-empty")
        if self.tract_count <= 0:
            raise ValueError(f"tract_count must be > 0, got {self.tract_count}")
        if not (0.0 <= self.avg_poverty_rate <= 1.0) or not (0.0 <= self.avg_no_vehicle_rate <= 1.0):
            raise ValueError("City baseline rates must be within [0, 1]")


@dataclass(frozen=True)
class EquityAuditReport:
    """Post-hoc outcome equity audit comparing recommended dispatch tracts to city baseline."""

    city: str
    recommended_count: int
    recommended_avg_poverty_rate: float
    city_avg_poverty_rate: float
    recommended_avg_no_vehicle_rate: float
    city_avg_no_vehicle_rate: float
    recommended_avg_median_age: float
    city_avg_median_age: float
    recommended_avg_median_income: float
    city_avg_median_income: float
    reaches_most_vulnerable: bool
    summary: str

    def __post_init__(self) -> None:
        if self.recommended_count <= 0:
            raise ValueError("recommended_count must be > 0")
        if not self.summary.strip():
            raise ValueError("summary must be non-empty")


@dataclass(frozen=True)
class AgentConfig:
    """Validated runtime configuration parsed once at process ingress."""

    project_id: str
    location: str
    dataset: str
    model_name: str
    predicted_label_col: str
    feature_columns: tuple[str, ...]
    target_city: str
    default_forecast_high_f: float
    query_timeout_sec: float
    max_results: int
    gemini_model: str
    mcp_toolbox_url: str | None = None
    mcp_toolbox_toolset: str = "climate_resilience_tools"

    def __post_init__(self) -> None:
        validate_sql_identifier(self.project_id, "project_id", allow_hyphen=True)
        validate_sql_identifier(self.dataset, "dataset")
        validate_sql_identifier(self.model_name, "model_name")
        validate_sql_identifier(self.predicted_label_col, "predicted_label_col")
        if not self.feature_columns:
            raise ValueError("feature_columns cannot be empty")
        for col in self.feature_columns:
            validate_sql_identifier(col, "feature_column")
        if not (1.0 <= self.query_timeout_sec <= 120.0):
            raise ValueError(f"query_timeout_sec must be in [1, 120], got {self.query_timeout_sec}")
        if not (1 <= self.max_results <= 10_000):
            raise ValueError(f"max_results must be in [1, 10000], got {self.max_results}")


def parse_agent_config(env: Mapping[str, str]) -> AgentConfig:
    """Parse environment variables into a validated AgentConfig at system boundary."""
    if not isinstance(env, Mapping):
        raise ValueError("env must be a key-value mapping")

    raw_project = env.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not raw_project or raw_project.lower() in _PLACEHOLDER_PROJECTS:
        raise ValueError(
            "GOOGLE_CLOUD_PROJECT must be set to a valid GCP project ID in environment/.env"
        )

    raw_features = env.get("BQ_FEATURE_COLS", "").strip()
    features = (
        tuple(col.strip() for col in raw_features.split(",") if col.strip())
        if raw_features
        else DEFAULT_FEATURE_COLUMNS
    )

    mcp_url = env.get("MCP_TOOLBOX_URL", "").strip() or None

    return AgentConfig(
        project_id=raw_project,
        location=env.get("GOOGLE_CLOUD_LOCATION", "US").strip() or "US",
        dataset=env.get("BQ_DATASET", "a4i_climate").strip() or "a4i_climate",
        model_name=env.get("BQ_MODEL_NAME", "heat_offset_model").strip() or "heat_offset_model",
        predicted_label_col=(
            env.get("BQ_PREDICTED_LABEL_COL", "predicted_degrees_above_city_average").strip()
            or "predicted_degrees_above_city_average"
        ),
        feature_columns=features,
        target_city=env.get("TARGET_CITY", "Dallas").strip() or "Dallas",
        default_forecast_high_f=float(env.get("DEFAULT_FORECAST_HIGH_F", "102.0")),
        query_timeout_sec=float(env.get("BQ_QUERY_TIMEOUT_SEC", "30.0")),
        max_results=int(env.get("BQ_MAX_RESULTS", "1000")),
        gemini_model=env.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash",
        mcp_toolbox_url=mcp_url,
        mcp_toolbox_toolset=(
            env.get("MCP_TOOLBOX_TOOLSET", "climate_resilience_tools").strip()
            or "climate_resilience_tools"
        ),
    )
