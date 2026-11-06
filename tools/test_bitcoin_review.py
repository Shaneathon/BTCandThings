import unittest
from bitcoin_review import review, stats


class BitcoinReviewTests(unittest.TestCase):
    def test_checkpoint_never_uses_future_and_counts_markets_not_refreshes(self):
        market=dict(market_slug='btc-updown-15m-test',window_start='2026-11-06T00:00:00Z',
                    window_end='2026-11-06T00:15:00Z',settlement_status='VERIFIED',official_winner='UP')
        def prediction(minute,p):
            return dict(market_slug=market['market_slug'],recorded_at=f'2026-11-06T00:{minute}:00Z',
                        predicted_up_probability=p,model_version='v1')
        report=review([market],{'Champion':[prediction('09',.8),prediction('10',.7),prediction('11',.99)],
                                'Challenger':[prediction('10',.6)]})
        entry=report['horizons']['300']
        self.assertEqual(entry['common_markets'],1)
        self.assertEqual(entry['models']['Champion: v1']['paired']['brier'],.09)
        self.assertEqual(entry['models']['Champion: v1']['paired']['markets'],1)
        market['settlement_status']='PENDING'
        self.assertEqual(review([market],{})['verified_btc_markets'],0)

    def test_unmatched_cohorts_not_compared_and_stale_checkpoints_excluded(self):
        market=dict(market_slug='btc-updown-15m-test',window_start='2026-11-06T00:00:00Z',
                    window_end='2026-11-06T00:15:00Z',settlement_status='VERIFIED',official_winner='DOWN')
        rows=[dict(market_slug=market['market_slug'],recorded_at='2026-11-06T00:08:00Z',
                   predicted_up_probability=.4,model_version='v1')]
        self.assertEqual(review([market],{'Champion':rows})['horizons']['300']['common_markets'],0)

    def test_calibration_boundaries_count_each_market_once(self):
        report=stats([(i,p,int(p>=.5)) for i,p in enumerate([0,.2,.4,.6,.8,1])])
        self.assertEqual(sum(b['markets'] for b in report['calibration']),6)
        self.assertEqual(report['markets'],6)


if __name__=='__main__':
    unittest.main()
