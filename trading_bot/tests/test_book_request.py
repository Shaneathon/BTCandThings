from email.message import Message
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
from trading_bot.book_request import request
from trading_bot.verify_runtime import public_book_report
from trading_bot.observed_paper import Engine
from trading_bot.tests.test_execution_audit import market,book,NOW

class RequestTests(unittest.TestCase):
    def test_unique_cache_key_preserves_contract_route_and_no_authentication(self):
        first,second=request('contract/a'),request('contract/a')
        self.assertEqual(urlsplit(first.full_url).path,'/v1/markets/contract%2Fa/book')
        self.assertNotEqual(first.full_url,second.full_url)
        self.assertEqual(first.get_method(),'GET')
        self.assertNotIn('Authorization',dict(first.header_items()))
        self.assertFalse(urlsplit(request('exact-contract',bypass=False).full_url).query)

    def test_probe_requires_fresh_headers_and_valid_book_not_just_successful_http(self):
        class Response:
            def __init__(self,age):
                from email.utils import formatdate
                self.headers=Message();self.headers['Age']=str(age);self.headers['Date']=formatdate(NOW,usegmt=True)
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,_): return json.dumps(book()).encode()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledger=root/'paper.sqlite';engine=Engine(ledger);engine.close()
            path=root/'input.json';path.write_text(json.dumps(dict(requested_market='btc-event',markets=[market()])))
            for age,expected in [(16,False),(0,True)]:
                with patch('trading_bot.verify_runtime.time.time',return_value=NOW),patch('urllib.request.urlopen',return_value=Response(age)):
                    result=public_book_report(path,ledger,NOW,bypass=True)
                self.assertEqual(result['fresh_response_verified'],expected)

if __name__=='__main__': unittest.main()
