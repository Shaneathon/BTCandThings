from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from trading_bot.input_packet import compact_markets,read_packet,encode_packet,required_markets,MAX_BYTES

NOW=1800000000

def iso(t): return datetime.fromtimestamp(t,timezone.utc).isoformat()
def market(slug,end):
    return dict(market_slug=slug,contract_slug='contract-'+slug,asset='BTC',duration_seconds=900,
                window_start=iso(end-900),window_end=iso(end),official_price_to_beat='100',
                settlement_status='VERIFIED',official_winner='UP',settled_at=iso(end+5),
                settlement_evidence='official-raw-'+('x'*12000))

class InputTests(unittest.TestCase):
    def test_large_history_is_compact_but_open_old_settlements_are_retained(self):
        rows=[market('closed'+str(i),NOW-100) for i in range(1000)]
        rows += [market('old-unneeded',NOW-172800),market('old-open-position',NOW-172800)]
        compact=compact_markets(iter(rows),NOW,{'old-open-position'})
        self.assertEqual(len(compact),1001)
        self.assertNotIn('old-unneeded',{m['market_slug'] for m in compact})
        pinned=next(m for m in compact if m['market_slug']=='old-open-position')
        self.assertEqual(pinned['official_winner'],'UP')
        self.assertEqual(pinned['settled_at'],rows[-1]['settled_at'])
        self.assertEqual(len(pinned['settlement_evidence']['sha256']),64)
        self.assertLess(len(encode_packet(dict(markets=compact))),1_000_000)
        self.assertGreater(len(json.dumps(rows).encode()),MAX_BYTES)
        self.assertTrue(rows[0]['settlement_evidence'].startswith('official-raw-'))

    def test_missing_required_market_and_oversized_output_are_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError,'OPEN_MARKET_MISSING'):
            compact_markets([],NOW,{'required'})
        with self.assertRaisesRegex(ValueError,'EXPORT_EXCEEDS'):
            encode_packet(dict(oversized='x'*MAX_BYTES))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'packet.json';path.write_bytes(b' '*(MAX_BYTES+1))
            with self.assertRaisesRegex(ValueError,'INPUT_TOO_LARGE'): read_packet(path)
            path.write_bytes(b'[]')
            with self.assertRaisesRegex(ValueError,'INPUT_NOT_AN_OBJECT'): read_packet(path)

    def test_pins_include_open_positions_and_proposed_orders_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.sqlite'
            self.assertEqual(required_markets(path),set())
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE positions(market_slug TEXT,payload TEXT)')
                db.execute('CREATE TABLE orders(market_slug TEXT,state TEXT,payload TEXT)')
                db.executemany('INSERT INTO positions VALUES(?,?)',[('open',json.dumps(dict(state='PAPER_OPEN'))),('closed',json.dumps(dict(state='PAPER_CLOSED')))])
                db.executemany('INSERT INTO orders VALUES(?,?,?)',[('pending::entry2','PROPOSED',json.dumps(dict(plan=dict(market_slug='pending')))),('rejected','REJECTED','{}')])
            before=path.read_bytes()
            self.assertEqual(required_markets(path),{'open','pending'})
            self.assertEqual(path.read_bytes(),before)

if __name__=='__main__': unittest.main()
