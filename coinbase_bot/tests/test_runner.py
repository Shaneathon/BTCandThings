from contextlib import redirect_stdout
from dataclasses import asdict
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from coinbase_bot.core import Config
from coinbase_bot.market_data import fetch_all
from coinbase_bot.runner import main
from coinbase_bot.tests.test_coinbase import public_fixture,NOW


class RunnerTests(unittest.TestCase):
    def test_tracker_feed_runs_paper_cycle_without_duplicate_public_requests(self):
        snapshots=fetch_all(NOW,public_fixture)
        report=dict(mode='RESEARCH_TRACKER',venue='Coinbase Advanced',orders_enabled=False,
                    observed_at=NOW,products={p:dict(bot_ready=True,bot_input=data) for p,data in snapshots.items()})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            config=root/'config.json';config.write_text(json.dumps(asdict(Config())))
            argv=['runner','--ledger',str(root/'paper.sqlite'),'--config',str(config),
                  '--kill-file',str(root/'STOP'),'--tracker-url','http://127.0.0.1:8767/status']
            output=io.StringIO()
            with patch('sys.argv',argv),patch.dict('os.environ',COIN_READ_TOKEN='private-fixture-read-token'),patch('coinbase_tracker.client.fetch',return_value=report) as fetched,patch('coinbase_tracker.client.time.time',return_value=NOW),patch('coinbase_bot.runner.time.time',return_value=NOW),patch('coinbase_bot.runner.fetch_all',side_effect=AssertionError('Duplicate Coinbase reads')),redirect_stdout(output):
                main()
            fetched.assert_called_once_with('http://127.0.0.1:8767/status','private-fixture-read-token')
            data=json.loads(output.getvalue())
            self.assertEqual(len(data['decisions']),4)
            self.assertFalse(data['account']['live_orders_enabled'])
            self.assertNotIn('private-fixture-read-token',output.getvalue())
            import sqlite3
            with sqlite3.connect(root/'paper.sqlite') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM decision_journal').fetchone()[0],4)

    def test_stale_tracker_cannot_create_paper_positions(self):
        from coinbase_tracker.client import bot_inputs
        with self.assertRaises(ValueError):
            bot_inputs(dict(mode='RESEARCH_TRACKER',venue='Coinbase Advanced',orders_enabled=False,
                            observed_at=NOW-121,products={}),now=NOW)
