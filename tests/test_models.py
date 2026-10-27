"""Tests for domain models, ingress parsing, and boundary invariants (Node 1)."""

from __future__ import annotations

import unittest

from agent.models import (
    AgentConfig,
    CandidateSite,
    CityBaseline,
    Coordinates,
    FeatureAttribution,
    InterventionType,
    parse_agent_config,
    validate_sql_identifier,
)


class TestModels(unittest.TestCase):
    def test_coordinates_valid_and_bounds(self) -> None:
        coord = Coordinates(latitude=32.7767, longitude=-96.7970)
        self.assertAlmostEqual(coord.latitude, 32.7767)
        self.assertAlmostEqual(coord.longitude, -96.7970)

        with self.assertRaisesRegex(ValueError, "latitude"):
            Coordinates(latitude=95.0, longitude=-96.7970)

        with self.assertRaisesRegex(ValueError, "longitude"):
            Coordinates(latitude=32.7767, longitude=-190.0)

    def test_validate_sql_identifier_rejects_injection(self) -> None:
        self.assertEqual(validate_sql_identifier("a4i_climate", "dataset"), "a4i_climate")
        self.assertEqual(
            validate_sql_identifier("my-gcp-project-123", "project_id", allow_hyphen=True),
            "my-gcp-project-123",
        )

        with self.assertRaisesRegex(ValueError, "Invalid SQL identifier"):
            validate_sql_identifier("a4i_climate; DROP TABLE", "dataset")

        with self.assertRaisesRegex(ValueError, "Invalid SQL identifier"):
            validate_sql_identifier("", "dataset")

    def test_parse_agent_config_enforces_required_project_and_bounds(self) -> None:
        env = {
            "GOOGLE_CLOUD_PROJECT": "test-climate-proj",
            "BQ_DATASET": "a4i_climate",
            "BQ_MODEL_NAME": "heat_offset_model",
            "TARGET_CITY": "Dallas",
            "DEFAULT_FORECAST_HIGH_F": "102.0",
            "BQ_QUERY_TIMEOUT_SEC": "25.0",
            "BQ_MAX_RESULTS": "500",
        }
        cfg = parse_agent_config(env)
        self.assertIsInstance(cfg, AgentConfig)
        self.assertEqual(cfg.project_id, "test-climate-proj")
        self.assertEqual(cfg.dataset, "a4i_climate")
        self.assertEqual(cfg.model_name, "heat_offset_model")
        self.assertEqual(cfg.target_city, "Dallas")
        self.assertAlmostEqual(cfg.default_forecast_high_f, 102.0)
        self.assertAlmostEqual(cfg.query_timeout_sec, 25.0)
        self.assertEqual(cfg.max_results, 500)
        self.assertIn("no_vehicle_rate", cfg.feature_columns)

    def test_parse_agent_config_rejects_missing_or_placeholder_project(self) -> None:
        with self.assertRaisesRegex(ValueError, "GOOGLE_CLOUD_PROJECT"):
            parse_agent_config({})

        with self.assertRaisesRegex(ValueError, "GOOGLE_CLOUD_PROJECT"):
            parse_agent_config({"GOOGLE_CLOUD_PROJECT": "your-gcp-project-id"})

    def test_candidate_site_validation_and_immutability(self) -> None:
        attr = FeatureAttribution(feature="no_vehicle_rate", attribution=2.4)
        site = CandidateSite(
            geo_id="48113002000",
            coordinates=Coordinates(latitude=32.7512, longitude=-96.8211),
            predicted_offset_f=6.5,
            total_pop=4200,
            median_age=68.5,
            median_income=28500.0,
            housing_units=1800,
            median_year_structure_built=1958,
            poverty_rate=0.34,
            no_vehicle_rate=0.29,
            attributions=(attr,),
        )
        self.assertEqual(site.geo_id, "48113002000")
        self.assertEqual(site.attributions[0].feature, "no_vehicle_rate")

        with self.assertRaisesRegex(ValueError, "geo_id"):
            CandidateSite(
                geo_id="bad",
                coordinates=Coordinates(latitude=32.75, longitude=-96.82),
                predicted_offset_f=5.0,
                total_pop=1000,
                median_age=40.0,
                median_income=50000.0,
                housing_units=400,
                median_year_structure_built=1980,
                poverty_rate=0.1,
                no_vehicle_rate=0.05,
                attributions=(),
            )

        with self.assertRaisesRegex(ValueError, "poverty_rate"):
            CandidateSite(
                geo_id="48113002000",
                coordinates=Coordinates(latitude=32.75, longitude=-96.82),
                predicted_offset_f=5.0,
                total_pop=1000,
                median_age=40.0,
                median_income=50000.0,
                housing_units=400,
                median_year_structure_built=1980,
                poverty_rate=1.5,
                no_vehicle_rate=0.05,
                attributions=(),
            )

    def test_city_baseline_validation(self) -> None:
        baseline = CityBaseline(
            city="Dallas",
            tract_count=520,
            avg_poverty_rate=0.14,
            avg_no_vehicle_rate=0.07,
            avg_median_age=33.5,
            avg_median_income=65000.0,
        )
        self.assertEqual(baseline.tract_count, 520)

        with self.assertRaisesRegex(ValueError, "tract_count"):
            CityBaseline(
                city="Dallas",
                tract_count=0,
                avg_poverty_rate=0.14,
                avg_no_vehicle_rate=0.07,
                avg_median_age=33.5,
                avg_median_income=65000.0,
            )

    def test_intervention_type_variants(self) -> None:
        self.assertEqual(InterventionType.HYDRATION_TRUCK.value, "hydration_truck")
        self.assertEqual(InterventionType.WELLNESS_CHECK.value, "wellness_check")


if __name__ == "__main__":
    unittest.main()
