"""Tests for parameterized BigQuery SQL builders and row parsers (Node 3)."""

from __future__ import annotations

import unittest

from agent.models import Coordinates, parse_agent_config
from agent.queries import (
    ParameterizedQuery,
    build_city_baseline_query,
    build_explain_point_query,
    build_explain_predict_tracts_query,
    build_station_frequency_query,
    parse_candidate_site_row,
    parse_city_baseline_row,
)


class TestQueries(unittest.TestCase):
    def setUp(self) -> None:
        self.config = parse_agent_config(
            {
                "GOOGLE_CLOUD_PROJECT": "dallas-heat-2026",
                "BQ_DATASET": "a4i_climate",
                "BQ_MODEL_NAME": "heat_offset_model",
                "TARGET_CITY": "Dallas",
            }
        )

    def test_build_explain_predict_tracts_query_uses_ml_explain_predict_and_params(self) -> None:
        q = build_explain_predict_tracts_query(
            self.config,
            min_lat=32.65,
            max_lat=32.85,
            min_lon=-96.95,
            max_lon=-96.70,
            limit=250,
        )
        self.assertIsInstance(q, ParameterizedQuery)
        self.assertIn("ML.EXPLAIN_PREDICT", q.sql)
        self.assertIn("`dallas-heat-2026.a4i_climate.heat_offset_model`", q.sql)
        self.assertIn("@min_lat", q.sql)
        self.assertEqual(q.params["min_lat"], 32.65)
        self.assertEqual(q.params["limit"], 250)

    def test_build_explain_point_query_uses_coordinates_parameters(self) -> None:
        target = Coordinates(latitude=32.7478, longitude=-96.8265)
        q = build_explain_point_query(self.config, target)
        self.assertIn("ML.EXPLAIN_PREDICT", q.sql)
        self.assertIn("ST_DISTANCE", q.sql)
        self.assertAlmostEqual(q.params["target_lat"], 32.7478)
        self.assertAlmostEqual(q.params["target_lon"], -96.8265)

    def test_build_city_baseline_and_station_frequency_queries(self) -> None:
        b_q = build_city_baseline_query(self.config)
        self.assertIn("`dallas-heat-2026.a4i_climate.tract_demographics`", b_q.sql)
        self.assertIn("AVG(poverty_rate)", b_q.sql)

        s_q = build_station_frequency_query(self.config, threshold_f=100.0)
        self.assertIn("`dallas-heat-2026.a4i_climate.station_daily_temps`", s_q.sql)
        self.assertIn("@threshold_f", s_q.sql)
        self.assertEqual(s_q.params["threshold_f"], 100.0)

    def test_parse_candidate_site_row_parses_nested_attributions(self) -> None:
        raw_row = {
            "geo_id": "48113002000",
            "latitude": 32.7512,
            "longitude": -96.8211,
            "predicted_degrees_above_city_average": 6.4,
            "total_pop": 4100,
            "median_age": 67.2,
            "median_income": 27500.0,
            "housing_units": 1650,
            "median_year_structure_built": 1956,
            "poverty_rate": 0.33,
            "no_vehicle_rate": 0.28,
            "top_feature_attributions": [
                {"feature": "no_vehicle_rate", "attribution": 2.35},
                {"feature": "median_year_structure_built", "attribution": 1.90},
            ],
        }
        site = parse_candidate_site_row(raw_row, self.config.predicted_label_col)
        self.assertEqual(site.geo_id, "48113002000")
        self.assertAlmostEqual(site.predicted_offset_f, 6.4)
        self.assertEqual(len(site.attributions), 2)
        self.assertEqual(site.attributions[0].feature, "no_vehicle_rate")
        self.assertAlmostEqual(site.attributions[0].attribution, 2.35)

    def test_parse_city_baseline_row(self) -> None:
        raw_row = {
            "tract_count": 518,
            "avg_poverty_rate": 0.145,
            "avg_no_vehicle_rate": 0.068,
            "avg_median_age": 33.8,
            "avg_median_income": 64200.0,
        }
        baseline = parse_city_baseline_row(raw_row, city="Dallas")
        self.assertEqual(baseline.city, "Dallas")
        self.assertEqual(baseline.tract_count, 518)
        self.assertAlmostEqual(baseline.avg_poverty_rate, 0.145)


if __name__ == "__main__":
    unittest.main()
