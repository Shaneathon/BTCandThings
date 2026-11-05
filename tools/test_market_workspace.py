"""Offline tests for market selector and verified price-to-beat."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "BTCandThings_Website" / "BTCandThings_Upload"))
from market_workspace import ASSETS, DURATIONS, event_slug, window_for, verified_target

class WorkspaceTests(unittest.TestCase):
    def test_all_twelve_selectable(self):
        self.assertEqual(len(ASSETS)*len(DURATIONS),12)
    def test_five_minute_slug(self):
        self.assertEqual(event_slug("ETH","5m",1793832900),"eth-updown-5m-2026-11-04-2255z")
    def test_unsupported_metal_five_minute(self):
        self.assertIsNone(event_slug("GOLD","5m",1793832900))
        self.assertIsNotNone(event_slug("GOLD","15m",1793832600))
    def test_boundaries(self):
        self.assertEqual(window_for(901, "5m"),(900,1200))
        self.assertEqual(window_for(901, "15m"),(900,1800))
    def test_typed_target_requires_correct_window(self):
        market={"assetPriceTerms":{"asset":{"symbol":"eth"},
                "marketType":"ASSET_PRICE_MARKET_TYPE_UP_DOWN",
                "windowStart":"2026-11-04T22:55:00Z",
                "windowEnd":"2026-11-04T23:00:00Z",
                "priceToBeat":{"value":"2400","currency":"USD"}}}
        self.assertEqual(verified_target(market,"ETH",1793832900,"5m"),2400)
        self.assertIsNone(verified_target(market,"ETH",1793832900,"15m"))
        self.assertIsNone(verified_target(market,"BTC",1793832900,"5m"))

if __name__=="__main__":
    unittest.main()
