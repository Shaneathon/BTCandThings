import os
import unittest
from unittest.mock import patch
from trading_bot.observed_paper import entry_in_scope, slots

class ScopeTests(unittest.TestCase):
    def test_scope_keeps_only_three_btc15_entry_wallets_and_preserves_registry(self):
        with patch.dict(os.environ, {'SHANEATHON_BTC15_ONLY':'1'}):
            eligible=[name for name,(asset,duration,_) in slots().items() if entry_in_scope(dict(asset=asset,duration_seconds=duration))]
            self.assertEqual(set(eligible),{'Champion','Challenger B','BTC_15m'})
            self.assertEqual(len(slots()),10)
            self.assertFalse(entry_in_scope({'asset':'ETH','duration_seconds':900}))
            self.assertFalse(entry_in_scope({'asset':'BTC','duration_seconds':300}))
    def test_default_scope_unchanged(self):
        with patch.dict(os.environ, {'SHANEATHON_BTC15_ONLY':''}):
            self.assertTrue(entry_in_scope({'asset':'ETH','duration_seconds':900}))
    def test_direct_entry_cannot_bypass_scope(self):
        from trading_bot.observed_paper import Engine
        with patch.dict(os.environ, {'SHANEATHON_BTC15_ONLY':'1'}):
            with self.assertRaisesRegex(ValueError,'MARKET_DISABLED'):
                Engine.propose(None,'ETH_15m',dict(asset='ETH',duration_seconds=900),None,None,{},0,0)

    def test_pending_non_btc_buy_rejected_without_book_or_cash_change(self):
        import json
        from trading_bot.tests.test_market_band import BandTests
        from trading_bot.tests.test_execution_audit import NOW
        fixture=BandTests();fixture.setUp()
        try:
            fixture.engine.propose('Champion',fixture.m,fixture.forecast,fixture.details,fixture.quotes(NOW),NOW,NOW)
            key,encoded=fixture.engine.db.execute('SELECT market_slug,payload FROM orders').fetchone()
            record=json.loads(encoded);record['market']['asset']='ETH'
            before=fixture.engine.db.execute('SELECT cash FROM wallets WHERE name="Champion"').fetchone()[0]
            with patch.dict(os.environ, {'SHANEATHON_BTC15_ONLY':'1'}):
                fixture.engine.complete('Champion',key,json.dumps(record),{},NOW+4)
            state=fixture.engine.db.execute('SELECT state FROM orders').fetchone()[0]
            self.assertEqual(state,'REJECTED')
            self.assertEqual(fixture.engine.db.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
            self.assertEqual(fixture.engine.db.execute('SELECT cash FROM wallets WHERE name="Champion"').fetchone()[0],before)
        finally: fixture.tearDown()
