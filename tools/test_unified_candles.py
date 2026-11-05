"""Offline checks for 12 unified market workspaces and proxy candles."""
import sys
import unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "BTCandThings_Website" / "BTCandThings_Upload"))
from market_candles import (clean_ohlc, load_candles, resample_complete,
                            indicators, candle_svg)
from market_workspace import ASSETS, DURATIONS, LISTED_DURATIONS


def frame(n=40):
    return pd.DataFrame({
        "time": pd.to_datetime([i*60 for i in range(n)], unit="s", utc=True),
        "open": [100+i for i in range(n)],
        "high": [101+i for i in range(n)],
        "low": [99+i for i in range(n)],
        "close": [100.5+i for i in range(n)],
        "volume": [10]*n})


class CandleTests(unittest.TestCase):
    def test_all_twelve_views_have_a_feed_configuration(self):
        self.assertEqual(len(ASSETS)*len(DURATIONS), 12)
        self.assertEqual(set(ASSETS), {"BTC","ETH","XRP","SOL","GOLD","SILVER"})
        for asset, config in ASSETS.items():
            self.assertTrue(config["pair"] or asset in ("GOLD","SILVER"))

    def test_incomplete_last_minute_excluded(self):
        rows = clean_ohlc(frame(7), 390)
        self.assertEqual(len(rows), 6)
        self.assertEqual(int(rows["time"].iloc[-1].timestamp()), 300)

    def test_five_minute_candle_requires_five_bars(self):
        rows = clean_ohlc(frame(7), 390)
        candles = resample_complete(rows, "5m", 390)
        self.assertEqual(len(candles), 1)
        self.assertEqual(float(candles.iloc[0]["open"]), 100)
        self.assertEqual(float(candles.iloc[0]["close"]), 104.5)

    def test_stale_data_disables_signals(self):
        rows = frame()
        self.assertTrue(indicators(rows, 5000)["stale"])
        fresh = indicators(rows, 2400)
        self.assertFalse(fresh["stale"])
        self.assertEqual(fresh["direction"], "UP")
        self.assertGreater(fresh["rsi"], 50)

    def test_svg_has_candle_wicks_and_target(self):
        svg = candle_svg(frame(10), "ETH", "1m", reference=105)
        self.assertIn("OFFICIAL TARGET", svg)
        self.assertIn("<rect", svg)
        self.assertIn("UTC", svg)

    def test_kraken_and_metals_sources_distinct(self):
        calls = []
        def fake(url, params):
            calls.append((url, params))
            if "kraken" in url:
                return {"result":{"XXBTZUSD":[
                    [i*60, 100, 101, 99, 100.5, 100.4, 10, 1]
                    for i in range(7)], "last": 0}}
            return {"chart":{"result":[{
                "timestamp":[i*60 for i in range(7)],
                "indicators":{"quote":[{
                    "open":[100]*7, "high":[101]*7,
                    "low":[99]*7, "close":[100.5]*7,
                    "volume":[10]*7}]}}]}}
        crypto, crypto_label = load_candles(fake, "BTC", "XBTUSD", 390)
        metal, metal_label = load_candles(fake, "GOLD", None, 390)
        self.assertEqual(len(crypto), 6)
        self.assertEqual(len(metal), 6)
        self.assertIn("Kraken", crypto_label)
        self.assertIn("futures proxy", metal_label)
        self.assertIn("GC%3DF", calls[1][0])

    def test_metals_five_minute_not_fabricated(self):
        self.assertNotIn("5m", LISTED_DURATIONS["GOLD"])
        self.assertNotIn("5m", LISTED_DURATIONS["SILVER"])


if __name__ == "__main__":
    unittest.main()
