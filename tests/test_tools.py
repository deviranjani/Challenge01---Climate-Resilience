"""Tests for imperative shell tools and ADK agent wiring with injected QueryRunner (Node 4)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence
import unittest

from agent.agent import build_system_instruction, parse_dotenv_lines
from agent.models import parse_agent_config
from agent.queries import ParameterizedQuery
from agent.tools import ClimateToolService, build_adk_tool_functions


class FakeQueryRunner:
    """Deterministic in-memory QueryRunner for testing tools without live BigQuery."""

    def __init__(self) -> None:
        self.queries_executed: list[ParameterizedQuery] = []

    def __call__(
        self,
        query: ParameterizedQuery,
        timeout_sec: float,
        max_results: int,
    ) -> Sequence[Mapping[str, Any]]:
        self.queries_executed.append(query)
        sql = query.sql
        if "ML.EXPLAIN_PREDICT" in sql:
            return [
                {
                    "geo_id": "48113001001",
                    "latitude": 32.7610,
                    "longitude": -96.8120,
                    "predicted_degrees_above_city_average": 7.4,
                    "total_pop": 6900,
                    "median_age": 31.5,
                    "median_income": 28000.0,
                    "housing_units": 2400,
                    "median_year_structure_built": 1984,
                    "poverty_rate": 0.34,
                    "no_vehicle_rate": 0.36,
                    "top_feature_attributions": [
                        {"feature": "no_vehicle_rate", "attribution": 2.8},
                        {"feature": "housing_units", "attribution": 2.1},
                    ],
                },
                {
                    "geo_id": "48113002002",
                    "latitude": 32.7320,
                    "longitude": -96.8350,
                    "predicted_degrees_above_city_average": 6.9,
                    "total_pop": 2300,
                    "median_age": 72.0,
                    "median_income": 23500.0,
                    "housing_units": 1100,
                    "median_year_structure_built": 1951,
                    "poverty_rate": 0.38,
                    "no_vehicle_rate": 0.32,
                    "top_feature_attributions": [
                        {"feature": "median_year_structure_built", "attribution": 3.0},
                        {"feature": "median_age", "attribution": 2.2},
                    ],
                },
            ]
        if "AVG(poverty_rate)" in sql:
            return [
                {
                    "tract_count": 520,
                    "avg_poverty_rate": 0.14,
                    "avg_no_vehicle_rate": 0.07,
                    "avg_median_age": 33.5,
                    "avg_median_income": 65000.0,
                }
            ]
        if "station_daily_temps" in sql:
            return [
                {"obs_year": 2023, "avg_hot_days_per_station": 42.5, "max_recorded_temp_f": 108.0},
                {"obs_year": 2024, "avg_hot_days_per_station": 46.0, "max_recorded_temp_f": 109.4},
            ]
        raise AssertionError(f"Unexpected query in FakeQueryRunner: {sql}")


class TestTools(unittest.TestCase):
    def setUp(self) -> None:
        self.config = parse_agent_config(
            {
                "GOOGLE_CLOUD_PROJECT": "dallas-heat-2026",
                "BQ_DATASET": "a4i_climate",
                "BQ_MODEL_NAME": "heat_offset_model",
                "TARGET_CITY": "Dallas",
            }
        )
        self.runner = FakeQueryRunner()
        self.service = ClimateToolService(config=self.config, runner=self.runner)

    def test_recommend_hydration_trucks_returns_ranked_stops_and_equity_audit(self) -> None:
        res = self.service.recommend_hydration_trucks(forecast_high_f=102.0, top_k=2)
        self.assertEqual(res["city"], "Dallas")
        self.assertEqual(res["intervention"], "hydration_truck")
        self.assertEqual(len(res["stops"]), 2)
        # Tract 48113001001 has higher pop + higher no_vehicle_rate -> Rank 1 for Hydration Truck
        self.assertEqual(res["stops"][0]["geo_id"], "48113001001")
        self.assertAlmostEqual(res["stops"][0]["expected_local_temp_f"], 109.4)
        self.assertTrue(res["equity_audit"]["reaches_most_vulnerable"])

    def test_recommend_wellness_checks_returns_elderly_older_housing_first(self) -> None:
        res = self.service.recommend_wellness_checks(forecast_high_f=102.0, top_k=2)
        self.assertEqual(res["city"], "Dallas")
        self.assertEqual(res["intervention"], "wellness_check")
        self.assertEqual(len(res["stops"]), 2)
        # Tract 48113002002 has median_age 72.0 & 1951 housing -> Rank 1 for Wellness Check
        self.assertEqual(res["stops"][0]["geo_id"], "48113002002")
        self.assertAlmostEqual(res["stops"][0]["expected_local_temp_f"], 108.9)
        self.assertTrue(res["equity_audit"]["reaches_most_vulnerable"])

    def test_explain_location_heat_risk_returns_point_attributions_and_scores(self) -> None:
        res = self.service.explain_location_heat_risk(
            latitude=32.7610,
            longitude=-96.8120,
            forecast_high_f=102.0,
        )
        self.assertEqual(res["geo_id"], "48113001001")
        self.assertAlmostEqual(res["predicted_offset_f"], 7.4)
        self.assertAlmostEqual(res["expected_local_temp_f"], 109.4)
        self.assertTrue(len(res["primary_drivers"]) >= 1)
        self.assertIn("hydration_truck_score", res)
        self.assertIn("wellness_check_score", res)

    def test_get_heat_wave_frequency_returns_yearly_station_series(self) -> None:
        res = self.service.get_heat_wave_frequency(threshold_f=100.0)
        self.assertEqual(res["city"], "Dallas")
        self.assertEqual(res["threshold_f"], 100.0)
        self.assertEqual(len(res["yearly_history"]), 2)
        self.assertEqual(res["yearly_history"][0]["obs_year"], 2023)

    def test_build_adk_tool_functions_and_system_instruction(self) -> None:
        tools = build_adk_tool_functions(config=self.config, runner=self.runner)
        self.assertEqual(len(tools), 4)
        hydration_fn, wellness_fn, explain_fn, freq_fn = tools
        self.assertEqual(hydration_fn(forecast_high_f=102.0, top_k=1)["intervention"], "hydration_truck")
        self.assertEqual(wellness_fn(forecast_high_f=102.0, top_k=1)["intervention"], "wellness_check")
        self.assertEqual(explain_fn(32.7610, -96.8120)["geo_id"], "48113001001")
        self.assertEqual(len(freq_fn(100.0)["yearly_history"]), 2)

        prompt = build_system_instruction("Dallas", 102.0)
        self.assertIn("Hydration Trucks", prompt)
        self.assertIn("Wellness Checks", prompt)
        self.assertIn("Outcome Equity Audit", prompt)

    def test_parse_dotenv_lines_parses_key_values_safely(self) -> None:
        lines = [
            "# comment line",
            "GOOGLE_CLOUD_PROJECT=my-dallas-proj",
            "TARGET_CITY = 'Dallas'",
            "",
        ]
        parsed = parse_dotenv_lines(lines)
        self.assertEqual(parsed["GOOGLE_CLOUD_PROJECT"], "my-dallas-proj")
        self.assertEqual(parsed["TARGET_CITY"], "Dallas")


if __name__ == "__main__":
    unittest.main()
