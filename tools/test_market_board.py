"""Pure validation tests for six-market radar; no network access."""
import sys
import types
import unittest
from pathlib import Path
from datetime import datetime, timezone
# market_board has no Streamlit dependency; UI receives st via dependency injection.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "BTCandThings_Website" / "BTCandThings_Upload"))
from market_board import ASSETS, market_slug, typed_reference, format_price

class MarketBoardTests(unittest.TestCase):
    def test_six_assets_and_slug(self):
        self.assertEqual([a[0] for a in ASSETS], ["BTC","ETH","XRP","SOL"])
        t = int(datetime(2026,11,4,20,15,tzinfo=timezone.utc).timestamp())
        self.assertEqual(market_slug("silver",t),"silver-updown-15m-2026-11-04-2015z")

    def test_reference_requires_exact_asset_window(self):
        t = int(datetime(2026,11,4,20,15,tzinfo=timezone.utc).timestamp())
        terms = {"asset":{"symbol":"eth"},"marketType":"ASSET_PRICE_MARKET_TYPE_UP_DOWN",
                 "windowStart":"2026-11-04T20:15:00Z","windowEnd":"2026-11-04T20:30:00Z",
                 "priceToBeat":{"currency":"USD","value":"2432.99"}}
        self.assertEqual(typed_reference({"assetPriceTerms":terms},("eth",),t),2432.99)
        self.assertIsNone(typed_reference({"assetPriceTerms":terms},("btc",),t))
        self.assertIsNone(typed_reference({"assetPriceTerms":terms},("eth",),t+900))
        self.assertIsNone(typed_reference({"priceToBeat":2432.99},("eth",),t))

    def test_display_does_not_invent(self):
        self.assertEqual(format_price("BTC",None),"PENDING")
        self.assertEqual(format_price("XRP",1.23),"$1.23000")

if __name__ == "__main__":
    unittest.main()
