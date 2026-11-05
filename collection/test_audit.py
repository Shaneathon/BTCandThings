import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from audit import audit, main
from collector import Store, collect
from test_collector import NOW, fixture_get


class AuditTests(unittest.TestCase):
    def test_complete_dataset_is_schema_shaped_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'data.sqlite'
            store = Store(path)
            collect(store, fixture_get, NOW)
            before = list(store.db.execute('SELECT * FROM records ORDER BY kind,key'))
            result = audit(path, NOW)
            self.assertTrue(result['healthy'])
            self.assertEqual(len(result['tables']['asset_proxy_candles']), 8)
            self.assertEqual(len(result['tables']['asset_market_windows']), 12)
            self.assertEqual(result['errors'], [])
            self.assertEqual(before, list(store.db.execute('SELECT * FROM records ORDER BY kind,key')))
            self.assertEqual(result, audit(path, NOW))
            store.db.close()

    def test_export_command_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'data.sqlite'
            output = Path(tmp)/'export.json'
            store = Store(path)
            collect(store, fixture_get, NOW)
            store.db.close()
            with patch('sys.argv', ['audit.py', '--db', str(path), '--out', str(output)]), patch('audit.time.time', return_value=NOW), patch('builtins.print'):
                with self.assertRaises(SystemExit) as result:
                    main()
                self.assertEqual(result.exception.code, 0)
                exported = json.loads(output.read_text())
                self.assertEqual(len(exported['tables']['asset_proxy_candles']), 8)
                with self.assertRaises(FileExistsError):
                    main()

    def test_missing_database_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'absent.sqlite'
            with self.assertRaises(sqlite3.OperationalError):
                audit(path, NOW)
            self.assertFalse(path.exists())

    def test_outage_recovery_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'data.sqlite'
            store = Store(path)
            def unavailable(*args):
                raise TimeoutError()
            collect(store, unavailable, NOW)
            self.assertFalse(audit(path, NOW)['healthy'])
            store.db.close()
            store = Store(path)
            collect(store, fixture_get, NOW)
            self.assertTrue(audit(path, NOW)['healthy'])
            # At a later observation, a stopped collector is detected.
            result = audit(path, NOW+3600)
            self.assertFalse(result['healthy'])
            self.assertTrue(all(r['stale'] and not r['current_market_verified'] for r in result['assets'].values()))
            store.db.close()

    def test_gap_and_unsupported_settlement_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'data.sqlite'
            store = Store(path)
            collect(store, fixture_get, NOW)
            kind, key, payload = store.db.execute("SELECT * FROM records WHERE kind='market' LIMIT 1").fetchone()
            row = json.loads(payload)
            row['settlement_status'] = 'VERIFIED'
            with store.db:
                store.db.execute('UPDATE records SET payload=? WHERE kind=? AND key=?', (json.dumps(row), kind, key))
            result = audit(path, NOW)
            self.assertFalse(result['healthy'])
            self.assertEqual(len(result['errors']), 1)
            kind, key, payload = store.db.execute("SELECT * FROM records WHERE kind='candle' ORDER BY key LIMIT 1").fetchone()
            row = json.loads(payload)
            from collector import epoch, iso
            row['candle_open'] = iso(epoch(row['candle_open'])-120)
            store.put('candle', [row])
            result = audit(path, NOW)
            self.assertGreater(result['assets'][row['asset']]['missing_minutes'], 0)
            store.db.close()


if __name__ == '__main__':
    unittest.main()
