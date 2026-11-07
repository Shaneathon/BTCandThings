import json
from pathlib import Path
import tempfile
import unittest
from trading_bot.activity import inspect
from trading_bot.observed_paper import Engine

class ActivityTests(unittest.TestCase):
    def test_empty_healthy_engine_reports_no_activity_without_claiming_a_fault(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledger=root/'paper.sqlite';data=root/'data.json'
            engine=Engine(ledger);engine.report(1000,True);engine.close()
            data.write_text(json.dumps(dict(exported_at=1000,markets=[],predictions=[])))
            before=ledger.read_bytes()
            result=inspect(ledger,data,1001)
            self.assertEqual(len(result['wallets']),10)
            self.assertTrue(all(w['orders_created_in_period']==0 for w in result['wallets']))
            self.assertTrue(all(w['current_state']=='NO_CURRENT_MARKET' for w in result['wallets']))
            self.assertEqual(result['input_age_seconds'],1)
            self.assertFalse(result['live_orders_enabled'])
            self.assertEqual(ledger.read_bytes(),before)

if __name__=='__main__': unittest.main()
