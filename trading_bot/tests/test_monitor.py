import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from trading_bot.core import PaperBot
from trading_bot.monitor import export, observe
from trading_bot.server import snapshot
from trading_bot.tests.test_bot import fixtures, NOW


class MonitorTests(unittest.TestCase):
    def test_real_input_snapshot_read_only_and_paper_entries_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output, ledger = (root / n for n in ('source.sqlite', 'input.json', 'paper.sqlite'))
            markets, predictions, _ = fixtures()
            with sqlite3.connect(source) as db:
                db.execute('CREATE TABLE records (kind TEXT,payload TEXT)')
                db.execute('CREATE TABLE research_snapshots (payload TEXT)')
                db.executemany('INSERT INTO records VALUES (?,?)', [('market', json.dumps(m)) for m in markets])
                db.executemany('INSERT INTO research_snapshots VALUES (?)', [(json.dumps(p),) for p in predictions])
            before = source.read_bytes()
            export(source, output)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            data = json.loads(output.read_text()); data['exported_at'] = NOW
            output.write_text(json.dumps(data))
            bot = PaperBot(ledger)
            report = observe(bot, output, NOW)
            self.assertEqual(report['input_status'], 'FRESH')
            self.assertTrue(report['decisions'])
            self.assertTrue(all(d['reason'] == 'KILL_SWITCH' for d in report['decisions']))
            self.assertFalse(report['account']['positions'])
            self.assertFalse(snapshot(ledger)['paper_entries_enabled'])
            self.assertFalse(report['account']['live_orders_enabled'])
            report = observe(bot, output, NOW + 181)
            self.assertEqual(report['input_status'], 'STALE_RESEARCH_EXPORT')
            self.assertEqual(report['input_markets'], 0)
            output.unlink()
            self.assertEqual(observe(bot, output, NOW + 182)['input_status'], 'RESEARCH_EXPORT_UNAVAILABLE')
            bot.close()
