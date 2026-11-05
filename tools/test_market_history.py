import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'BTCandThings_Website'/'BTCandThings_Upload'))
from market_history import load_history, summarize, reader

MARKET=dict(market_slug='eth-test',asset='ETH',duration_seconds=300,window_start='2026-11-05T12:00:00Z',
            window_end='2026-11-05T12:05:00Z',settlement_status='VERIFIED',official_winner='UP',settlement_evidence='official record')
PREDICTION=dict(market_slug='eth-test',recorded_at='2026-11-05T12:01:00Z',source_timestamp='2026-11-05T12:00:00Z',
                model_version='research-v1',predicted_up_probability=.8)


class HistoryTests(unittest.TestCase):
    def test_first_observation_scored_once_and_no_other_asset_history(self):
        later={**PREDICTION,'recorded_at':'2026-11-05T12:02:00Z','predicted_up_probability':.1}
        result=summarize([MARKET],[later,PREDICTION],'ETH',300)
        score=result['models']['research-v1']
        self.assertEqual(score['markets'],1)
        self.assertEqual(score['accuracy'],1)
        self.assertAlmostEqual(score['brier'],.04)
        self.assertEqual(summarize([MARKET],[PREDICTION],'BTC',300)['models'],{})
        self.assertEqual(summarize([MARKET],[PREDICTION],'ETH',900)['models'],{})

    def test_pending_and_future_leaking_predictions_excluded(self):
        self.assertEqual(summarize([{**MARKET,'settlement_status':'PENDING'}],[PREDICTION],'ETH',300)['models'],{})
        bad={**PREDICTION,'source_timestamp':'2026-11-05T12:02:00Z'}
        result=summarize([MARKET],[bad],'ETH',300)
        self.assertEqual(result['models'],{})
        self.assertEqual(result['invalid_predictions'],1)

    def test_cohort_pagination_and_only_read_operations(self):
        calls=[]
        def get(table,params):
            calls.append((table,params))
            if table=='asset_market_windows':
                return [MARKET]
            self.assertEqual(params['market_slug'],'in.(eth-test)')
            return [PREDICTION]*1000 if params['offset']=='0' else []
        result=load_history(get,'ETH','5m')
        self.assertEqual(len(calls),3)
        self.assertEqual(result['models']['research-v1']['markets'],1)
        self.assertIn('20 verified',result['cohort'])

    def test_refuse_partial_history(self):
        def get(table,params):
            return [MARKET] if table=='asset_market_windows' else [PREDICTION]*1000
        with self.assertRaises(ValueError):
            load_history(get,'ETH','5m')

    def test_empty_history_and_unsafe_url(self):
        self.assertEqual(load_history(lambda *args: [],'SOL','15m')['models'],{})
        with self.assertRaises(ValueError):
            reader('https://user:password@example.com','not-real')


if __name__=='__main__':
    unittest.main()
