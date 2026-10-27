"""Pure functional core for Today-track Hydration Truck and Wellness Check dispatch ranking."""

from __future__ import annotations

import heapq
import math
from typing import Sequence

from agent.models import (
    CandidateSite,
    CityBaseline,
    DispatchStop,
    EquityAuditReport,
    FeatureAttribution,
    InterventionType,
)


def format_feature_attributions(
    attributions: Sequence[FeatureAttribution],
    top_n: int = 3,
) -> tuple[str, ...]:
    """Format top ML.EXPLAIN_PREDICT attributions ordered by absolute magnitude."""
    if top_n <= 0:
        raise ValueError(f"top_n must be > 0, got {top_n}")
    if not attributions:
        return ()

    ranked = heapq.nlargest(top_n, attributions, key=lambda a: abs(a.attribution))
    return tuple(f"{attr.attribution:+.1f}°F from {attr.feature}" for attr in ranked)


def score_hydration_truck(site: CandidateSite) -> float:
    """Compute priority score for mobile Hydration Truck deployment.

    Hydration trucks target outdoor/transit-dependent corridors with high heat offset,
    high share of carless households (walking/waiting at transit), high poverty,
    and large exposed population volume.
    """
    if not isinstance(site, CandidateSite):
        raise TypeError("site must be a CandidateSite instance")
    if site.total_pop < 0:
        raise ValueError("site.total_pop must be non-negative")

    heat_factor = max(0.0, site.predicted_offset_f + 5.0)
    transit_dependence = site.no_vehicle_rate * 40.0
    poverty_exposure = site.poverty_rate * 25.0
    pop_scale = min(30.0, math.log1p(site.total_pop) * 3.2)

    return round(heat_factor * 3.0 + transit_dependence + poverty_exposure + pop_scale, 2)


def score_wellness_check(site: CandidateSite) -> float:
    """Compute priority score for door-to-door Wellness Check deployment.

    Wellness checks target indoor/isolated residents who cannot self-evacuate:
    elderly population (median_age), pre-modern housing stock (older build year),
    carless households (no_vehicle_rate), low income/poverty, and high heat offset.
    """
    if not isinstance(site, CandidateSite):
        raise TypeError("site must be a CandidateSite instance")
    if site.median_age < 0.0:
        raise ValueError("site.median_age must be non-negative")

    heat_factor = max(0.0, site.predicted_offset_f + 5.0)
    age_vulnerability = max(0.0, site.median_age - 30.0) * 0.9
    housing_age_penalty = max(0.0, float(2000 - site.median_year_structure_built)) * 0.35
    isolation_factor = site.no_vehicle_rate * 32.0 + site.poverty_rate * 28.0

    return round(
        heat_factor * 2.8 + age_vulnerability + housing_age_penalty + isolation_factor,
        2,
    )


def _build_rationale(
    intervention: InterventionType,
    site: CandidateSite,
    expected_temp_f: float,
    drivers: tuple[str, ...],
) -> str:
    """Construct a dispatcher-ready rationale string for a single stop."""
    driver_text = ", ".join(drivers) if drivers else "local urban surface geometry"
    if intervention == InterventionType.HYDRATION_TRUCK:
        return (
            f"Hydration Truck Stop — Tract {site.geo_id} "
            f"({site.coordinates.latitude:.4f}, {site.coordinates.longitude:.4f}): "
            f"Expected {expected_temp_f:.1f}°F ({site.predicted_offset_f:+.1f}°F offset; "
            f"drivers: {driver_text}). Serves {site.total_pop:,} residents with "
            f"{site.no_vehicle_rate * 100:.1f}% carless households and "
            f"{site.poverty_rate * 100:.1f}% poverty."
        )
    return (
        f"Wellness Check Zone — Tract {site.geo_id} "
        f"({site.coordinates.latitude:.4f}, {site.coordinates.longitude:.4f}): "
        f"Expected {expected_temp_f:.1f}°F ({site.predicted_offset_f:+.1f}°F offset; "
        f"drivers: {driver_text}). High indoor risk: median age {site.median_age:.1f} yrs, "
        f"median housing built {site.median_year_structure_built}, "
        f"{site.no_vehicle_rate * 100:.1f}% without vehicles, "
        f"{site.poverty_rate * 100:.1f}% poverty."
    )


def rank_dispatch_stops(
    candidates: Sequence[CandidateSite],
    intervention: InterventionType,
    forecast_high_f: float,
    top_k: int = 5,
) -> tuple[DispatchStop, ...]:
    """Rank candidate tracts in O(N log K) time for Today-track emergency dispatch."""
    if not candidates:
        raise ValueError("candidates must be a non-empty sequence")
    if top_k <= 0 or top_k > 100:
        raise ValueError(f"top_k must be in [1, 100], got {top_k}")
    if not math.isfinite(forecast_high_f) or not (40.0 <= forecast_high_f <= 140.0):
        raise ValueError(f"forecast_high_f must be in [40, 140], got {forecast_high_f}")

    scorer = (
        score_hydration_truck
        if intervention == InterventionType.HYDRATION_TRUCK
        else score_wellness_check
    )
    scored = ((scorer(site), site) for site in candidates)
    top_sites = heapq.nlargest(top_k, scored, key=lambda pair: (pair[0], pair[1].predicted_offset_f))

    stops: list[DispatchStop] = []
    for idx, (score, site) in enumerate(top_sites, start=1):
        expected_temp = round(forecast_high_f + site.predicted_offset_f, 1)
        drivers = format_feature_attributions(site.attributions, top_n=3)
        rationale = _build_rationale(intervention, site, expected_temp, drivers)
        stops.append(
            DispatchStop(
                rank=idx,
                intervention=intervention,
                site=site,
                expected_local_temp_f=expected_temp,
                priority_score=score,
                primary_drivers=drivers,
                operational_rationale=rationale,
            )
        )
    return tuple(stops)


def audit_outcome_equity(
    stops: Sequence[DispatchStop],
    baseline: CityBaseline,
) -> EquityAuditReport:
    """Compare recommended dispatch stops against city-wide tract_demographics averages."""
    if not stops:
        raise ValueError("stops must be non-empty for outcome equity audit")
    if not isinstance(baseline, CityBaseline):
        raise TypeError("baseline must be a CityBaseline instance")

    n = len(stops)
    rec_poverty = sum(s.site.poverty_rate for s in stops) / n
    rec_no_veh = sum(s.site.no_vehicle_rate for s in stops) / n
    rec_age = sum(s.site.median_age for s in stops) / n
    rec_income = sum(s.site.median_income for s in stops) / n

    reaches_vulnerable = (
        rec_poverty >= baseline.avg_poverty_rate
        and rec_no_veh >= baseline.avg_no_vehicle_rate
        and rec_income <= baseline.avg_median_income
    )

    verdict = (
        "PASS — Recommendations prioritize high-vulnerability neighborhoods"
        if reaches_vulnerable
        else "WARNING — Recommendations under-index on one or more vulnerability dimensions"
    )
    summary = (
        f"{verdict} in {baseline.city} (n={n} sites vs {baseline.tract_count} city tracts): "
        f"Poverty {rec_poverty * 100:.1f}% vs city {baseline.avg_poverty_rate * 100:.1f}%, "
        f"No-Vehicle {rec_no_veh * 100:.1f}% vs city {baseline.avg_no_vehicle_rate * 100:.1f}%, "
        f"Median Age {rec_age:.1f} vs city {baseline.avg_median_age:.1f}, "
        f"Median Income ${rec_income:,.0f} vs city ${baseline.avg_median_income:,.0f}."
    )

    return EquityAuditReport(
        city=baseline.city,
        recommended_count=n,
        recommended_avg_poverty_rate=round(rec_poverty, 4),
        city_avg_poverty_rate=round(baseline.avg_poverty_rate, 4),
        recommended_avg_no_vehicle_rate=round(rec_no_veh, 4),
        city_avg_no_vehicle_rate=round(baseline.avg_no_vehicle_rate, 4),
        recommended_avg_median_age=round(rec_age, 2),
        city_avg_median_age=round(baseline.avg_median_age, 2),
        recommended_avg_median_income=round(rec_income, 2),
        city_avg_median_income=round(baseline.avg_median_income, 2),
        reaches_most_vulnerable=reaches_vulnerable,
        summary=summary,
    )
