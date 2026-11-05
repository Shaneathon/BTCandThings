"""No-network tests of the experimental champion/challenger pipeline."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from challenger_research import (VARIANTS, MIN_MARKETS, build_rows, compare,
                                 shifted_probability, bootstrap_delta_interval)


class ChallengerTests(unittest.TestCase):
    def test_direction_of_momentum(self):
        base = .5
        self.assertGreater(shifted_probability(base, .001, .20), base)
        self.assertLess(shifted_probability(base, .001, -.20), base)
        self.assertAlmostEqual(shifted_probability(base, 0, .4), base)

    def test_no_future_spot_leakage_and_early_only(self):
        t = datetime(2026, 11, 4, tzinfo=timezone.utc)
        iso = lambda d: d.isoformat()
        market = {"market_slug":"m", "window_start":iso(t),
                  "window_end":iso(t+timedelta(minutes=15)),
                  "settlement_status":"VERIFIED", "official_winner":"UP"}
        p = [
            {"market_slug":"prior", "recorded_at":iso(t-timedelta(minutes=3)),
             "kraken_spot":100, "predicted_up_probability":.5},
            {"market_slug":"m", "recorded_at":iso(t), "kraken_spot":101,
             "predicted_up_probability":.6},
            {"market_slug":"m", "recorded_at":iso(t+timedelta(minutes=6)),
             "kraken_spot":130, "predicted_up_probability":.99}]
        rows, c = build_rows([market], p)
        self.assertEqual(c["eligible_markets"], 1)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["champion"], .6)
        self.assertGreater(rows[0]["challengers"]["momentum_mild"], .6)

    def test_insufficient_data_does_not_promote(self):
        result = compare([], {"eligible_markets":0})
        self.assertEqual(result["status"], "insufficient_data")
        self.assertFalse(result["live_model_changed"])

    def test_training_selection_not_holdout_selection(self):
        t = datetime(2026, 11, 4, tzinfo=timezone.utc)
        rows = []
        for i in range(MIN_MARKETS):
            # Train favors momentum; holdout favors champion.
            y = 1 if i < int(MIN_MARKETS*.6) else 0
            rows.append({"market_slug":str(i), "time":t+timedelta(minutes=15*i),
                         "actual":y, "champion":.5,
                         "challengers":{name:(.8 if coef>0 else .2)
                                        for name,coef in VARIANTS.items()}})
        result = compare(rows, {"eligible_markets":len(rows)})
        self.assertEqual(result["status"], "evaluated")
        self.assertFalse(result["promising_for_prospective_test"])
        self.assertEqual(result["selected_challenger"], "momentum_mild")
        self.assertEqual(result["holdout_markets"], 100)

    def test_bootstrap_deterministic(self):
        rows = [{"actual":1,"champion":.5,"challengers":{"x":.6}}]*10
        self.assertEqual(bootstrap_delta_interval(rows,"x",reps=100),
                         bootstrap_delta_interval(rows,"x",reps=100))


if __name__ == "__main__":
    unittest.main()
