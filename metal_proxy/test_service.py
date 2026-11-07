from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
from metal_proxy.service import Store,validate,retry_time

NOW=1794009600


def quote(asset,when,price=4000):
    return dict(symbol='XAU' if asset=='GOLD' else 'XAG',currency='USD',exchangeRate=1,
                price=price,updatedAt=datetime.fromtimestamp(when,timezone.utc).isoformat())


class MetalsTests(unittest.TestCase):
    def test_sampled_candles_use_real_source_times_and_no_partial_backfill(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(Path(temporary)/'quotes.sqlite')
            for minute in range(51):
                for offset in (5,25,45):
                    source=NOW+minute*60+offset
                    store.put('GOLD',quote('GOLD',source,4000+minute+offset/100),source+1)
            data=store.candles('GOLD',NOW+51*60)
            self.assertEqual(data['completed_candles'],51)
            self.assertFalse(data['is_official_settlement_feed'])
            self.assertIsNone(data['candles'][0]['volume'])
            self.assertEqual(data['candles'][0]['sample_count'],3)
            self.assertEqual(len(store.candles('GOLD',NOW+50*60+46)['candles']),50)
            store.close()

    def test_duplicates_stale_future_wrong_instruments_and_conflicts_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(Path(temporary)/'quotes.sqlite')
            store.put('SILVER',quote('SILVER',NOW,52),NOW+1)
            store.put('SILVER',quote('SILVER',NOW,52),NOW+20)
            self.assertEqual(store.db.execute('SELECT count(*) FROM quotes').fetchone()[0],1)
            self.assertEqual(store.candles('SILVER',NOW+60)['candles'],[])
            for payload,observed in [(quote('SILVER',NOW,53),NOW+1),(quote('GOLD',NOW),NOW+1),
                                     (quote('SILVER',NOW),NOW+121),(quote('SILVER',NOW+1),NOW)]:
                with self.assertRaises(ValueError): store.put('SILVER',payload,observed)
            store.close()

    def test_gaps_are_not_filled_and_only_contiguous_suffix_returned(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(Path(temporary)/'quotes.sqlite')
            for minute in (0,1,3,4):
                for offset in (5,45):
                    source=NOW+minute*60+offset
                    store.put('SILVER',quote('SILVER',source,52),source+1)
            data=store.candles('SILVER',NOW+300)
            self.assertEqual([row['time'] for row in data['candles']],[NOW+180,NOW+240])
            store.close()

    def test_retry_after_respected(self):
        class Limited: headers={'Retry-After':'120'}
        self.assertEqual(retry_time(Limited(),NOW),NOW+120)
