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

    def test_historical_version_does_not_empty_current_pairwise_comparison(self):
        def market(slug, day):
            return dict(market_slug='btc-updown-15m-'+slug,
                        window_start=f'2026-11-{day}T00:00:00Z',
                        window_end=f'2026-11-{day}T00:15:00Z',
                        settlement_status='VERIFIED',official_winner='UP')
        old,current=market('old','05'),market('current','06')
        def prediction(m, day, model, p):
            return dict(market_slug=m['market_slug'],recorded_at=f'2026-11-{day}T00:10:00Z',
                        model_version=model,predicted_up_probability=p)
        report=review([old,current],{'Champion':[prediction(old,'05','old',.5),
                                                 prediction(current,'06','current',.6)],
                                    'Challenger':[prediction(current,'06','A',.8)]})
        horizon=report['horizons']['300']
        self.assertEqual(horizon['common_markets'],0)
        self.assertEqual(len(horizon['pairwise']),1)
        pair=horizon['pairwise'][0]
        self.assertEqual(pair['champion'],'Champion: current')
        self.assertEqual(pair['markets'],1)
        self.assertAlmostEqual(pair['all']['challenger_minus_champion_brier'],-.12)


if __name__=='__main__':
    unittest.main()
