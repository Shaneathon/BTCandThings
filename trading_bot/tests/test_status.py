from functools import partial
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from trading_bot.core import PaperBot
from trading_bot.server import Handler, snapshot
from trading_bot.status_client import read_status


class StatusTests(unittest.TestCase):
    def test_read_only_http_authentication_and_no_mutation_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ledger.sqlite'
            bot=PaperBot(path)
            bot.cycle([],[],[],1800000060)
            bot.close()
            token='synthetic-test-token-32-characters-long'
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,ledger=path,token=token))
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                def call(method,path,auth=None):
                    connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    connection.request(method,path,headers={'Authorization':auth} if auth else {})
                    response=connection.getresponse()
                    result=(response.status,response.read())
                    connection.close()
                    return result
                self.assertEqual(call('GET','/status')[0],401)
                self.assertEqual(call('GET','/unknown','Bearer '+token)[0],404)
                status,body=call('GET','/status','Bearer '+token)
                self.assertEqual(status,200)
                self.assertFalse(json.loads(body)['account']['live_orders_enabled'])
                self.assertNotIn(token.encode(),body)
                self.assertEqual(call('POST','/status','Bearer '+token)[0],501)
                self.assertEqual(snapshot(path)['account']['cash'],'1000')
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def test_reader_rejects_unsafe_destinations(self):
        for url in ('http://example.com/status','https://user:key@example.com/status','https://example.com/order','https://example.com/status?token=x'):
            with self.assertRaises(ValueError): read_status(url,'x'*32)


if __name__=='__main__':
    unittest.main()
