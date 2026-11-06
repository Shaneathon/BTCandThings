"""Asset isolation, timing, and research forecast checks for uniform trackers."""
from pathlib import Path
import sys
import unittest
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'BTCandThings_Website'/'BTCandThings_Upload'))
from tracker_panels import countdown_html, research_signal, signal_card
from market_workspace import verified_target


def candles(scale=1, falling=False):
    prices = [(150-i*.2 if falling else 100+i*.2)*scale for i in range(60)]
    return pd.DataFrame(dict(time=pd.to_datetime([i*60 for i in range(60)],unit='s',utc=True), close=prices))


class TrackerTests(unittest.TestCase):
    def test_asset_local_baselines_and_complements(self):
        rising = research_signal(candles(), 3600, 3900, 110)
        falling = research_signal(candles(falling=True), 3600, 3900, 145)
        self.assertTrue(rising['ready'])
        self.assertEqual(rising['direction'], 'UP')
        self.assertEqual(falling['direction'], 'DOWN')
        self.assertGreater(rising['probability'], .5)
        self.assertLess(falling['probability'], .5)
        self.assertAlmostEqual(research_signal(candles(10),3600,3900,1100)['probability'],rising['probability'])

    def test_same_momentum_different_contract_target_and_expiry(self):
        # A shared asset feed legitimately has the same momentum, while the
        # separately verified contract windows can have opposite forecasts.
        short = research_signal(candles(), 3600, 3900, 110)
        long = research_signal(candles(), 3600, 4500, 120)
        self.assertEqual(short['direction'], long['direction'])
        self.assertGreater(short['probability'], .5)
        self.assertLess(long['probability'], .5)

    def test_paused_for_stale_gapped_future_closed_and_insufficient(self):
        gapped = candles().drop(index=[10])
        for frame, now, end in [(candles(),4000,4500), (gapped,3600,3900),
                                (candles(),3500,3900), (candles(),3600,3600),
                                (candles().tail(30),3600,3900)]:
            with self.subTest(now=now, end=end, count=len(frame)):
                self.assertFalse(research_signal(frame,now,end,110)['ready'])

    def test_no_target_no_probability_but_lean_available(self):
        self.assertIsNone(research_signal(candles(),3600,3900)['probability'])
        self.assertEqual(research_signal(candles(),3600,3900)['direction'],'UP')

    def test_foreign_asset_or_duration_never_supplies_target(self):
        market={'assetPriceTerms':{'asset':{'symbol':'eth'},'marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                'windowStart':'1970-01-01T01:00:00Z','windowEnd':'1970-01-01T01:05:00Z',
                'priceToBeat':{'value':110,'currency':'USD'}}}
        self.assertEqual(verified_target(market,'ETH',3600,'5m'),110)
        for asset in ('BTC','XRP','SOL'):
            self.assertIsNone(verified_target(market,asset,3600,'5m'))
        self.assertIsNone(verified_target(market,'ETH',3600,'15m'))
        market['assetPriceTerms']['windowEnd']='1970-01-01T01:05:00'
        self.assertIsNone(verified_target(market,'ETH',3600,'5m'))

    def test_countdown_fixed_window_and_unverified_state(self):
        timer=countdown_html('ETH','5m',3600,3900,3650,110,True)
        self.assertIn('ETH 5m WINDOW',timer)
        self.assertIn('"end": 3900',timer)
        self.assertIn('performance.now()',timer)
        self.assertIn('WINDOW CLOSED',timer)
        self.assertNotIn('Date.now()',timer)
        pending=countdown_html('SOL','15m',3600,4500,3650,None,False)
        self.assertIn('CONTRACT UNVERIFIED',pending)
        self.assertIn('PENDING',pending)

    def test_signal_card_escapes_content(self):
        card=signal_card('<script>', 'UP', '<img>')
        self.assertNotIn('<script>',card)
        self.assertIn('signal-up',card)


if __name__=='__main__':
    unittest.main()
