from functools import partial
from http.server import ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.parse import urlencode
from trading_bot.observed_paper import Engine
from trading_bot.trade_history import page
from trading_bot.server import Handler
from trading_bot.status_client import read_trades

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'paper.sqlite';self.now=time.time()
        engine=Engine(self.path)
        for i in range(65):
            p=dict(market_slug='market'+str(i),asset='BTC',duration_seconds=900,side='UP',quantity='5',entry_price='.24',
                fees='.05',cost='1.25',state='PAPER_CLOSED',payout='0',pnl='-1.25',opened_at=self.now-i-1,closed_at=self.now-i,
                window_start=self.now-i-900,window_end=self.now-i-2)
            engine.db.execute('INSERT INTO positions VALUES(?,?,?)',('Champion',p['market_slug'],json.dumps(p)))
        engine.db.commit();engine.close()

    def tearDown(self): self.tmp.cleanup()

    def test_all_pages_include_old_trades_and_anchor_prevents_new_fills_shifting_them(self):
        before=self.path.read_bytes()
        first=page(self.path,'Champion',1,50,self.now,now=self.now)
        second=page(self.path,'Champion',2,50,self.now,now=self.now)
        self.assertEqual(first['total_filled_trades'],65)
        self.assertEqual(first['page_count'],2)
        self.assertEqual(len(first['trades']),50);self.assertEqual(len(second['trades']),15)
        self.assertFalse({r['market_slug'] for r in first['trades']} & {r['market_slug'] for r in second['trades']})
        self.assertEqual(first['trades'][0]['result'],'LOST')
        self.assertEqual(self.path.read_bytes(),before)
        import sqlite3
        with sqlite3.connect(self.path) as db:
            p=dict(market_slug='new-fill',opened_at=self.now+1,state='PAPER_OPEN')
            db.execute('INSERT INTO positions VALUES(?,?,?)',('Champion','new-fill',json.dumps(p)))
        stable=page(self.path,'Champion',2,50,self.now,now=self.now+2)
        self.assertEqual([r['market_slug'] for r in stable['trades']],[r['market_slug'] for r in second['trades']])
        self.assertEqual(page(self.path,'Champion',1,50,self.now+2,now=self.now+2)['total_filled_trades'],66)

    def test_unknown_wallet_oversized_page_and_future_anchor_reject(self):
        for kwargs in [dict(wallet='unknown'),dict(limit=10000),dict(number=0),dict(as_of=self.now+100)]:
            with self.assertRaises(ValueError): page(self.path,now=self.now,**kwargs)
        self.assertEqual(page(self.path,'ETH_5m',as_of=self.now,now=self.now)['total_filled_trades'],0)

    def test_history_endpoint_requires_auth_and_read_only_client_accepts_it(self):
        token='fixture-read-token-not-a-secret-123456'
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,ledger=self.path,token=token))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            c=http.client.HTTPConnection('127.0.0.1',server.server_port)
            c.request('GET','/trades?wallet=Champion');r=c.getresponse();self.assertEqual(r.status,401);r.read();c.close()
            response=read_trades('http://127.0.0.1:'+str(server.server_port)+'/status',token,'Champion',2,self.now)
            self.assertEqual(len(response['trades']),15)
            self.assertFalse(response['account']['live_orders_enabled'])
        finally: server.shutdown();thread.join();server.server_close()

if __name__=='__main__': unittest.main()
