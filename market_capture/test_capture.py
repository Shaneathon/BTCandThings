import gzip
import json
from pathlib import Path
import tempfile
import unittest
from market_capture.coinbase_ws import Archive,CapturePaused


class CaptureTests(unittest.TestCase):
    def test_raw_messages_preserve_wire_and_connection_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive=Archive(temporary,minimum_free=0)
            wire=json.dumps(dict(channel='l2_data',sequence_num=12,events=[{'type':'snapshot','product_id':'BTC-USD'}]))
            archive.write(wire,'connection-a',now=1794000000)
            archive.write(wire,'connection-b',now=1794000001)
            archive.close_segment()
            files=list(Path(temporary).glob('*.gz'))
            self.assertEqual(len(files),1)
            with gzip.open(files[0],'rt') as stream: rows=[json.loads(line) for line in stream]
            self.assertEqual([r['connection_id'] for r in rows],['connection-a','connection-b'])
            self.assertEqual(rows[0]['wire_json'],wire)
            self.assertEqual(files[0].stat().st_mode & 0o777,0o600)
            self.assertFalse(archive.status['book_ready'])
            self.assertFalse(archive.status['real_trading'])
            archive.save_status()
            self.assertEqual(json.loads((Path(temporary)/'status.json').read_text())['session_messages'],2)

    def test_daily_budget_survives_restart_and_does_not_delete_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive=Archive(temporary,minimum_free=0)
            archive.write('{"channel":"heartbeats"}','a',now=1794000000);archive.close_segment()
            before={p.name:p.read_bytes() for p in Path(temporary).glob('*.gz')}
            restarted=Archive(temporary,daily_limit=1,minimum_free=0)
            with self.assertRaises(CapturePaused): restarted.write('{"channel":"heartbeats"}','b',now=1794000001)
            self.assertEqual(before,{p.name:p.read_bytes() for p in Path(temporary).glob('*.gz')})
