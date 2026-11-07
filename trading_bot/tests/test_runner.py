from contextlib import redirect_stdout
from dataclasses import asdict,replace
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from trading_bot.core import Config
from trading_bot.runner import main
from trading_bot.tests.test_bot import fixtures,NOW
from trading_bot.server import snapshot


class RunnerTests(unittest.TestCase):
    def test_real_collector_format_to_paper_ledger_without_source_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            collector,ledger,quotes,config=(root/n for n in ('source.sqlite','paper.sqlite','quotes.json','config.json'))
            markets,predictions,book=fixtures()
            with sqlite3.connect(collector) as db:
                db.execute('CREATE TABLE records (kind TEXT,payload TEXT)')
                db.execute('CREATE TABLE research_snapshots (payload TEXT)')
                db.executemany('INSERT INTO records VALUES (?,?)',[('market',json.dumps(m)) for m in markets])
                db.executemany('INSERT INTO research_snapshots VALUES (?)',[(json.dumps(p),) for p in predictions])
            before=collector.read_bytes()
            quotes.write_text(json.dumps(book))
            config.write_text(json.dumps(asdict(replace(Config(),minimum_settled_markets=2))))
            argv=['runner','--collector-db',str(collector),'--ledger',str(ledger),'--quotes',str(quotes),
                  '--config',str(config),'--kill-file',str(root/'STOP')]
            output=io.StringIO()
            with patch('sys.argv',argv),patch('trading_bot.runner.time.time',return_value=NOW),redirect_stdout(output):
                main()
            report=json.loads(output.getvalue())
            self.assertEqual(len(report['account']['positions']),8)
            self.assertEqual(before,collector.read_bytes())
            self.assertFalse(snapshot(ledger)['account']['live_orders_enabled'])

    def test_ledger_cannot_be_collector_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.sqlite'
            path.write_text('preserve source')
            argv=['runner','--collector-db',str(path),'--ledger',str(path),'--quotes','unused',
                  '--config','unused','--kill-file','unused']
            with patch('sys.argv',argv),redirect_stdout(io.StringIO()),patch('sys.stderr',io.StringIO()),self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code,2)
            self.assertEqual(path.read_text(),'preserve source')


if __name__=='__main__':
    unittest.main()
