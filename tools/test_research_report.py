"""Offline checks for research_report.py; no network or secrets required."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_report import evaluate, wilson

class AuditTests(unittest.TestCase):
    def test_one_prediction_per_market_and_verified_only(self):
        markets = [
            {"market_slug":"a","window_start":"2026-11-04T00:00:00Z","settlement_status":"VERIFIED","official_winner":"UP"},
            {"market_slug":"b","window_start":"2026-11-04T00:15:00Z","settlement_status":"VERIFIED","official_winner":"DOWN"},
            {"market_slug":"c","window_start":"2026-11-04T00:30:00Z","settlement_status":"PENDING","official_winner":"UP"}]
        preds = [
            {"market_slug":"a","recorded_at":"2026-11-04T00:01:00Z","predicted_up_probability":0.7,"model_version":"v1"},
            {"market_slug":"a","recorded_at":"2026-11-04T00:10:00Z","predicted_up_probability":0.1,"model_version":"v1"},
            {"market_slug":"b","recorded_at":"2026-11-04T00:16:00Z","predicted_up_probability":0.3,"model_version":"v1"},
            {"market_slug":"c","recorded_at":"2026-11-04T00:31:00Z","predicted_up_probability":0.8,"model_version":"v1"}]
        r = evaluate(markets, preds)
        self.assertEqual(r["verified_markets"], 2)
        self.assertEqual(r["verified_markets_with_valid_predictions"], 2)
        self.assertEqual(r["correct"], 2)
        self.assertEqual(r["accuracy"], 1.0)
        self.assertEqual(r["usable_prediction_rows_for_verified_markets"], 3)
        self.assertEqual(r["brier"], 0.09)
    def test_empty(self):
        r = evaluate([], [])
        self.assertIsNone(r["accuracy"])
        self.assertIsNone(wilson(0, 0))
    def test_neutral_excluded_from_accuracy(self):
        r = evaluate([], [], [
            {"horizon_minutes":3,"evaluated_at":"2026-11-04T00:03:00Z","predicted_direction":"NEUTRAL","direction_correct":None},
            {"horizon_minutes":3,"evaluated_at":"2026-11-04T00:03:00Z","predicted_direction":"UP","direction_correct":True}])
        self.assertEqual(r["lean_forecast_horizons"]["3"]["scored_non_neutral"], 1)

if __name__ == "__main__":
    unittest.main()
