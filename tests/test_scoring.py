"""Tests for pure functional core: Hydration Truck vs Wellness Check scoring, ranking, and equity audit (Node 2)."""

from __future__ import annotations

import unittest

from agent.models import (
    CandidateSite,
    CityBaseline,
    Coordinates,
    FeatureAttribution,
    InterventionType,
)
from agent.scoring import (
    audit_outcome_equity,
    format_feature_attributions,
    rank_dispatch_stops,
    score_hydration_truck,
    score_wellness_check,
)


def _make_site(
    geo_id: str,
    offset_f: float,
    total_pop: int,
    median_age: float,
    median_income: float,
    year_built: int,
    poverty_rate: float,
    no_vehicle_rate: float,
    attributions: tuple[FeatureAttribution, ...] = (),
) -> CandidateSite:
    return CandidateSite(
        geo_id=geo_id,
        coordinates=Coordinates(latitude=32.7500, longitude=-96.8000),
        predicted_offset_f=offset_f,
        total_pop=total_pop,
        median_age=median_age,
        median_income=median_income,
        housing_units=max(100, total_pop // 2),
        median_year_structure_built=year_built,
        poverty_rate=poverty_rate,
        no_vehicle_rate=no_vehicle_rate,
        attributions=attributions,
    )


class TestScoring(unittest.TestCase):
    def setUp(self) -> None:
        # Site A: High population, high transit dependence (no vehicle), younger working population -> Hydration Truck priority
        self.site_transit_corridor = _make_site(
            geo_id="48113001001",
            offset_f=7.2,
            total_pop=6800,
            median_age=31.0,
            median_income=29000.0,
            year_built=1985,
            poverty_rate=0.32,
            no_vehicle_rate=0.35,
            attributions=(
                FeatureAttribution("housing_units", 3.1),
                FeatureAttribution("no_vehicle_rate", 2.2),
                FeatureAttribution("median_income", -0.4),
            ),
        )
        # Site B: Older residents, older pre-AC housing (1952), high isolation -> Wellness Check priority
        self.site_elderly_isolated = _make_site(
            geo_id="48113002002",
            offset_f=6.8,
            total_pop=2400,
            median_age=71.5,
            median_income=24000.0,
            year_built=1952,
            poverty_rate=0.36,
            no_vehicle_rate=0.31,
            attributions=(
                FeatureAttribution("median_year_structure_built", 2.9),
                FeatureAttribution("median_age", 2.1),
            ),
        )
        # Site C: Affluent, cool, high car ownership -> Low priority for both
        self.site_affluent_cool = _make_site(
            geo_id="48113003003",
            offset_f=-1.5,
            total_pop=3500,
            median_age=38.0,
            median_income=125000.0,
            year_built=2012,
            poverty_rate=0.03,
            no_vehicle_rate=0.01,
            attributions=(FeatureAttribution("median_income", -1.8),),
        )

    def test_format_feature_attributions_orders_by_magnitude(self) -> None:
        attrs = (
            FeatureAttribution("median_income", -0.4),
            FeatureAttribution("housing_units", 3.14),
            FeatureAttribution("no_vehicle_rate", -2.25),
        )
        formatted = format_feature_attributions(attrs, top_n=2)
        self.assertEqual(len(formatted), 2)
        self.assertEqual(formatted[0], "+3.1°F from housing_units")
        self.assertEqual(formatted[1], "-2.2°F from no_vehicle_rate")

    def test_hydration_truck_vs_wellness_check_differentiation(self) -> None:
        # Hydration trucks prioritize high-pop + high-no-vehicle outdoor/transit corridors
        ht_corridor = score_hydration_truck(self.site_transit_corridor)
        ht_elderly = score_hydration_truck(self.site_elderly_isolated)
        ht_affluent = score_hydration_truck(self.site_affluent_cool)
        self.assertGreater(ht_corridor, ht_elderly)
        self.assertGreater(ht_elderly, ht_affluent)

        # Wellness checks prioritize elderly + older housing + immobile/low-income residents
        wc_elderly = score_wellness_check(self.site_elderly_isolated)
        wc_corridor = score_wellness_check(self.site_transit_corridor)
        wc_affluent = score_wellness_check(self.site_affluent_cool)
        self.assertGreater(wc_elderly, wc_corridor)
        self.assertGreater(wc_corridor, wc_affluent)

    def test_rank_dispatch_stops_bounds_and_ordering(self) -> None:
        candidates = (
            self.site_affluent_cool,
            self.site_elderly_isolated,
            self.site_transit_corridor,
        )
        hydration_stops = rank_dispatch_stops(
            candidates,
            intervention=InterventionType.HYDRATION_TRUCK,
            forecast_high_f=102.0,
            top_k=2,
        )
        self.assertEqual(len(hydration_stops), 2)
        self.assertEqual(hydration_stops[0].rank, 1)
        self.assertEqual(hydration_stops[0].site.geo_id, "48113001001")
        self.assertAlmostEqual(hydration_stops[0].expected_local_temp_f, 109.2)
        self.assertIn("Hydration Truck", hydration_stops[0].operational_rationale)

        wellness_stops = rank_dispatch_stops(
            candidates,
            intervention=InterventionType.WELLNESS_CHECK,
            forecast_high_f=102.0,
            top_k=2,
        )
        self.assertEqual(len(wellness_stops), 2)
        self.assertEqual(wellness_stops[0].rank, 1)
        self.assertEqual(wellness_stops[0].site.geo_id, "48113002002")
        self.assertAlmostEqual(wellness_stops[0].expected_local_temp_f, 108.8)
        self.assertIn("Wellness Check", wellness_stops[0].operational_rationale)

    def test_rank_dispatch_stops_rejects_invalid_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidates"):
            rank_dispatch_stops((), InterventionType.HYDRATION_TRUCK, 102.0, top_k=3)

        with self.assertRaisesRegex(ValueError, "top_k"):
            rank_dispatch_stops(
                (self.site_transit_corridor,),
                InterventionType.HYDRATION_TRUCK,
                102.0,
                top_k=0,
            )

    def test_audit_outcome_equity_verifies_vulnerability_targeting(self) -> None:
        baseline = CityBaseline(
            city="Dallas",
            tract_count=520,
            avg_poverty_rate=0.14,
            avg_no_vehicle_rate=0.07,
            avg_median_age=33.5,
            avg_median_income=65000.0,
        )
        stops = rank_dispatch_stops(
            (self.site_transit_corridor, self.site_elderly_isolated),
            intervention=InterventionType.WELLNESS_CHECK,
            forecast_high_f=102.0,
            top_k=2,
        )
        report = audit_outcome_equity(stops, baseline)
        self.assertTrue(report.reaches_most_vulnerable)
        self.assertEqual(report.recommended_count, 2)
        self.assertGreater(report.recommended_avg_poverty_rate, baseline.avg_poverty_rate)
        self.assertGreater(report.recommended_avg_no_vehicle_rate, baseline.avg_no_vehicle_rate)
        self.assertLess(report.recommended_avg_median_income, baseline.avg_median_income)


if __name__ == "__main__":
    unittest.main()
