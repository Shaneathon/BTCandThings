import json
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal
from trading_bot.automatic_review import review,pause
from trading_bot.observed_paper import Engine,SETTINGS
from trading_bot.tests.test_execution_audit import NOW


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'paper.sqlite';self.engine=Engine(self.path)
        self.engine.report(NOW,True)

    def tearDown(self): self.engine.close();self.tmp.cleanup()

    def seed(self,count=14,version=None,offset=0):
        with self.engine.db:
            for i in range(count):
                p=dict(market_slug='old'+str(i)+str(offset),asset='BTC',duration_seconds=300,fees='0',payout='0',state='PAPER_CLOSED',pnl='-1.5',cost='1.5',opened_at=NOW-1000+i+offset,closed_at=NOW-500+i+offset,
                       entry_limits=dict(version=version or SETTINGS['version']))
                self.engine.db.execute('INSERT INTO positions VALUES(?,?,?)',('BTC_5m','old'+str(i)+str(offset),json.dumps(p)))

    def test_pause_is_wallet_local_preserves_finances_and_does_not_extend_on_same_losses(self):
        self.seed();before=self.engine.db.execute('SELECT * FROM wallets').fetchall()
        report=review(self.path,NOW)
        row=next(r for r in report['wallets'] if r['wallet']=='BTC_5m')
        self.assertEqual(row['status'],'PAUSED_NEW')
        self.assertEqual(self.engine.risk('BTC_5m',NOW),0)
        self.assertEqual(self.engine.risk('ETH_5m',NOW),Decimal('1.50'))
        self.assertEqual(self.engine.db.execute('SELECT * FROM wallets').fetchall(),before)
        self.assertEqual(review(self.path,NOW+10)['state'],'SKIPPED_RECENT_REVIEW')
        until=row['entry_pause']['paused_until']
        self.engine.report(until+1,True)
        second=review(self.path,until+1)
        row=next(r for r in second['wallets'] if r['wallet']=='BTC_5m')
        self.assertEqual(row['status'],'INSUFFICIENT_NEW_TRADES')
        self.assertTrue(row['previous_pause_expired'])
        self.assertIsNone(pause(self.engine.db,'BTC_5m',until+1))
        self.assertEqual(self.engine.risk('BTC_5m',until+1),Decimal('1.50'))

    def test_small_samples_and_old_entry_policy_do_not_trigger(self):
        self.seed(9);report=review(self.path,NOW)
        self.assertTrue(all(r['entry_pause'] is None for r in report['wallets']))
        self.seed(10,'OBSERVED_PAPER_V1',offset=50)
        self.engine.report(NOW+3600,True)
        report=review(self.path,NOW+3600)
        row=next(r for r in report['wallets'] if r['wallet']=='BTC_5m')
        self.assertEqual(row['closed_trades'],9)
        self.assertEqual(row['excluded_other_entry_policies'],10)
        self.assertIsNone(row['entry_pause'])

    def test_stale_or_live_snapshot_never_triggers_action(self):
        self.seed()
        with self.assertRaisesRegex(ValueError,'identity/freshness'): review(self.path,NOW+61)
        report=self.engine.report(NOW,True);report['account']['live_orders_enabled']=True
        with self.engine.db: self.engine.db.execute('UPDATE bot_snapshot SET payload=?',(json.dumps(report),))
        with self.assertRaisesRegex(ValueError,'identity/freshness'): review(self.path,NOW)
        self.assertFalse(self.engine.db.execute('SELECT 1 FROM automatic_entry_pauses').fetchone())

    def test_open_positions_settle_while_new_entries_are_paused(self):
        from trading_bot.tests.test_observed_paper import ObservedTests
        from trading_bot.tests.test_execution_audit import iso
        fixture=ObservedTests();fixture.setUp()
        try:
            e=fixture.engine
            e.propose('Champion',fixture.m,fixture.p,fixture.details,fixture.quotes(NOW),NOW,NOW-1)
            payload=e.db.execute('SELECT payload FROM orders').fetchone()[0]
            e.complete('Champion',fixture.m['market_slug'],payload,fixture.quotes(NOW+4),NOW+4)
            with e.db: e.db.execute('INSERT INTO automatic_entry_pauses VALUES(?,?,?,?)',('Champion',NOW+5,NOW+21600,'test'))
            fixture.m.update(settlement_status='VERIFIED',official_winner='UP',settled_at=iso(NOW+61),settlement_evidence='official typed prices')
            e.settle([fixture.m],NOW+62)
            self.assertEqual(json.loads(e.db.execute('SELECT payload FROM positions').fetchone()[0])['state'],'PAPER_CLOSED')
            self.assertEqual(e.risk('Champion',NOW+62),0)
        finally: fixture.tearDown()

    def test_pending_order_cannot_fill_after_automatic_pause(self):
        from trading_bot.tests.test_observed_paper import ObservedTests
        fixture=ObservedTests();fixture.setUp()
        try:
            engine=fixture.engine
            engine.propose('Champion',fixture.m,fixture.p,fixture.details,fixture.quotes(NOW),NOW,NOW-1)
            payload=engine.db.execute('SELECT payload FROM orders').fetchone()[0]
            with engine.db: engine.db.execute('INSERT INTO automatic_entry_pauses VALUES(?,?,?,?)',('Champion',NOW,NOW+21600,'test'))
            engine.complete('Champion',fixture.m['market_slug'],payload,fixture.quotes(NOW+4),NOW+4)
            self.assertFalse(engine.db.execute('SELECT 1 FROM positions').fetchone())
            self.assertEqual(engine.db.execute('SELECT cash FROM wallets WHERE name="Champion"').fetchone()[0],'1000')
            self.assertEqual(json.loads(engine.db.execute('SELECT result FROM orders').fetchone()[0])['reason'],'AUTOMATIC_ENTRY_PAUSE')
        finally: fixture.tearDown()

if __name__=='__main__': unittest.main()
