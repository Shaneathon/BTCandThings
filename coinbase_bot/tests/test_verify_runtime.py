import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from coinbase_bot.verify_runtime import tracker_report,activity_report,LIMIT
from coinbase_bot.observed import ObservedBot
from coinbase_bot.tests.test_coinbase import NOW,public_fixture
from coinbase_bot.market_data import fetch_product

class VerifyTests(unittest.TestCase):
    def test_sizes_ages_and_activity_are_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'tracker.sqlite';ledger=root/'bot.sqlite'
            snapshot=fetch_product('BTC-USD',NOW,public_fixture)
            data=dict(mode='RESEARCH_TRACKER',orders_enabled=False,products={'BTC-USD':dict(bot_ready=True,bot_input=snapshot)})
            with sqlite3.connect(source) as db:
                db.execute('CREATE TABLE tracker_status(id INTEGER,observed_at REAL,payload TEXT)')
                db.execute('INSERT INTO tracker_status VALUES(1,?,?)',(NOW,json.dumps(data)))
            bot=ObservedBot(ledger);bot.cycle({'BTC-USD':snapshot},NOW);bot.close()
            before=(source.read_bytes(),ledger.read_bytes())
            result=tracker_report(source,NOW+1)
            self.assertTrue(result['below_client_size_limit'])
            self.assertTrue(result['products'][0]['meets_engine_time_limits'])
            self.assertFalse(tracker_report(source,NOW+30)['products'][0]['meets_engine_time_limits'])
            self.assertEqual(activity_report(ledger,NOW+1,6)['orders_created_in_period'],{'PROPOSED':1})
            self.assertEqual((source.read_bytes(),ledger.read_bytes()),before)

if __name__=='__main__': unittest.main()
