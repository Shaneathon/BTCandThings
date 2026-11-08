from dataclasses import asdict,replace
from decimal import Decimal
import copy,json
import unittest
from trading_bot.observed_paper import SETTINGS,cycle
from trading_bot.entry_policy import phase,observe,reserve_slot
from trading_bot.paper_exits import update_trail,manage,finish
from trading_bot.execution_model import simulate
from trading_bot.tests.test_execution_audit import NOW,iso
from trading_bot.tests.test_execution_model import plan,book


class TrailingTests(unittest.TestCase):
    def setUp(self):
        from trading_bot.tests.test_observed_paper import ObservedTests
        self.f=ObservedTests();self.f.setUp();self.e=self.f.engine
    def tearDown(self): self.f.tearDown()

    def buy(self):
        self.e.propose('Champion',self.f.m,self.f.p,self.f.details,self.f.quotes(NOW),NOW,NOW-1)
        key,encoded=self.e.db.execute("SELECT market_slug,payload FROM orders WHERE state='PROPOSED'").fetchone()
        self.e.complete('Champion',key,encoded,self.f.quotes(NOW+4),NOW+4)
        return key,json.loads(self.e.db.execute('SELECT payload FROM positions WHERE market_slug=?',(key,)).fetchone()[0])

    def packet(self,up,stamp):
        p=dict(self.f.p,recorded_at=iso(stamp),predicted_up_probability=str(up))
        return dict(exported_at=stamp,markets=[self.f.m],predictions=[p],execution_evidence=dict(metadata={self.f.m['market_slug']:self.f.details}))

    def test_full_window_early_entries_and_no_ordinary_last_two_minutes(self):
        m=dict(self.f.m,window_start=iso(NOW-100),window_end=iso(NOW+800))
        self.assertEqual(phase(self.e.db,'Champion',m,self.f.p,NOW,SETTINGS)['phase'],'NORMAL')
        with self.e.db: self.e.db.execute('DELETE FROM signal_observations')
        with self.assertRaisesRegex(ValueError,'LATE_REVERSAL'): phase(self.e.db,'Champion',self.f.m,self.f.p,NOW,SETTINGS)
        m=dict(self.f.m,window_end=iso(NOW+14))
        with self.assertRaisesRegex(ValueError,'ENTRY_WINDOW'): phase(self.e.db,'Champion',m,self.f.p,NOW,SETTINGS)

    def test_reversal_is_observed_same_window_and_stale_signals_do_not_qualify(self):
        self.assertEqual(phase(self.e.db,'Champion',self.f.m,self.f.p,NOW,SETTINGS)['phase'],'LATE_MODEL_REVERSAL')
        with self.assertRaisesRegex(ValueError,'LATE_REVERSAL'): phase(self.e.db,'Champion',self.f.m,dict(self.f.p,recorded_at=iso(NOW-31)),NOW,SETTINGS)
        with self.e.db: self.e.db.execute('UPDATE signal_observations SET market_slug="another-window"')
        with self.assertRaisesRegex(ValueError,'LATE_REVERSAL'): phase(self.e.db,'Champion',self.f.m,self.f.p,NOW,SETTINGS)

    def test_order_crossing_into_final_two_minutes_is_rechecked_before_fill(self):
        with self.e.db: self.e.db.execute('DELETE FROM signal_observations')
        m=dict(self.f.m,window_start=iso(NOW-779),window_end=iso(NOW+121))
        self.f.m=m
        self.f.details['assetPriceTerms'].update(windowStart=m['window_start'],windowEnd=m['window_end'])
        self.e.propose('Champion',m,self.f.p,self.f.details,self.f.quotes(NOW),NOW,NOW-1)
        key,payload=self.e.db.execute('SELECT market_slug,payload FROM orders').fetchone()
        self.e.complete('Champion',key,payload,self.f.quotes(NOW+4),NOW+4)
        self.assertFalse(self.e.db.execute('SELECT 1 FROM positions').fetchone())
        self.assertEqual(json.loads(self.e.db.execute('SELECT result FROM orders').fetchone()[0])['reason'],'LATE_REVERSAL_REQUIRED')

    def test_peak_ratchets_and_exit_triggers_at_five_points_without_fixed_target(self):
        key,p=self.buy()
        # Entry signal is .9, not the cheap market ask. A .96 reading raises the peak.
        update_trail(self.e,'Champion',key,p,self.packet('.96',NOW+5),NOW+5)
        update_trail(self.e,'Champion',key,p,self.packet('.92',NOW+6),NOW+6)
        self.assertIsNone(self.e.db.execute('SELECT triggered_at FROM probability_trails').fetchone()[0])
        update_trail(self.e,'Champion',key,p,self.packet('.91',NOW+7),NOW+7)
        row=self.e.db.execute('SELECT peak,triggered_at FROM probability_trails').fetchone()
        self.assertEqual(row,('0.96',NOW+7))
        update_trail(self.e,'Champion',key,p,self.packet('.99',NOW+8),NOW+8)
        self.assertEqual(self.e.db.execute('SELECT triggered_at FROM probability_trails').fetchone()[0],NOW+7)

    def test_down_probability_is_complement_and_stale_or_wrong_model_ignored(self):
        key,p=self.buy();p=dict(p,side='DOWN')
        with self.e.db:
            payload=json.loads(self.e.db.execute('SELECT payload FROM orders').fetchone()[0]);payload['signal']['predicted_up_probability']='.45'
            self.e.db.execute('UPDATE orders SET payload=?',(json.dumps(payload),))
        update_trail(self.e,'Champion',key,p,self.packet('.28',NOW+5),NOW+5)
        self.assertEqual(self.e.db.execute('SELECT peak FROM probability_trails').fetchone()[0],'0.72')
        update_trail(self.e,'Champion',key,p,self.packet('.33',NOW+6),NOW+6)
        self.assertEqual(self.e.db.execute('SELECT current,triggered_at FROM probability_trails').fetchone(),('0.67',NOW+6))
        update_trail(self.e,'Champion',key,p,self.packet('.9',NOW-100),NOW+7)
        self.assertEqual(self.e.db.execute('SELECT current FROM probability_trails').fetchone()[0],'0.67')

    def test_delayed_bid_exit_fees_restart_and_settlement_do_not_double_pay(self):
        key,p=self.buy();cash=Decimal(self.e.db.execute("SELECT cash FROM wallets WHERE name='Champion'").fetchone()[0])
        data=self.packet('.80',NOW+5)
        def quotes(m,after=0): return self.f.quotes(NOW+5 if not after else NOW+8)
        manage(self.e,data,quotes,NOW+5,True,lambda:NOW+5)
        oid,wallet,key,encoded=self.e.db.execute('SELECT order_id,wallet,entry_key,payload FROM exit_orders').fetchone()
        finish(self.e,oid,wallet,key,encoded,quotes(self.f.m),NOW+6)
        self.assertEqual(self.e.db.execute('SELECT state FROM exit_orders').fetchone()[0],'PROPOSED')
        thin=self.f.quotes(NOW+8)
        for row in thin['UP']['liquidation_bids']: row['quantity']='1'
        finish(self.e,oid,wallet,key,encoded,thin,NOW+8)
        self.assertEqual(self.e.db.execute('SELECT state FROM exit_orders').fetchone()[0],'REJECTED')
        # A fresh retry has another identity and cannot fill before its own delay.
        manage(self.e,self.packet('.8',NOW+9),lambda m,after=0:self.f.quotes(NOW+9),NOW+9,True,lambda:NOW+9)
        oid,wallet,key,encoded=self.e.db.execute("SELECT order_id,wallet,entry_key,payload FROM exit_orders WHERE state='PROPOSED'").fetchone()
        from trading_bot.observed_paper import Engine
        self.e.close();self.e=Engine(self.f.path);self.f.engine=self.e
        finish(self.e,oid,wallet,key,encoded,self.f.quotes(NOW+12),NOW+12)
        closed=json.loads(self.e.db.execute('SELECT payload FROM positions WHERE market_slug=?',(key,)).fetchone()[0])
        self.assertEqual(closed['close_reason'],'MODEL_PROBABILITY_TRAILING_EXIT')
        self.assertEqual(Decimal(closed['payout'])-Decimal(closed['cost']),Decimal(closed['pnl']))
        self.assertGreater(Decimal(closed['exit_fees']),0)
        after=self.e.db.execute("SELECT cash FROM wallets WHERE name='Champion'").fetchone()[0]
        self.assertEqual(Decimal(after),cash+Decimal(closed['payout']))
        finish(self.e,oid,wallet,key,encoded,self.f.quotes(NOW+12),NOW+12)
        self.f.m.update(settlement_status='VERIFIED',official_winner='UP',settled_at=iso(NOW+61),settlement_evidence='official')
        self.e.settle([self.f.m],NOW+62)
        self.assertEqual(self.e.db.execute("SELECT cash FROM wallets WHERE name='Champion'").fetchone()[0],after)

    def test_sell_fok_requires_fresh_bids_and_never_uses_ask_for_profit(self):
        selling=replace(plan(),intent='ORDER_INTENT_SELL_LONG',limit_price='.50')
        data=dict(book(),intent='ORDER_INTENT_SELL_LONG',bids=[dict(price='.56',quantity='100')])
        result=simulate(selling,data,103)
        self.assertEqual(result['gross_proceeds'],'5.60')
        self.assertEqual(result['net_proceeds'],'5.50')
        self.assertEqual(result['total_cost'],'0')
        data['bids'][0]['quantity']='4'
        result=simulate(selling,data,103)
        self.assertEqual(result['filled_quantity'],'0');self.assertEqual(result['fees'],'0')
        data['bids'][0]['quantity']='100';data['request_started_at']=101
        self.assertEqual(simulate(selling,data,103)['state'],'REJECTED')

    def test_market_price_movement_alone_does_not_trigger_probability_stop(self):
        key,p=self.buy()
        def forbidden(*args): raise AssertionError('No exit quote should be requested without a model trigger')
        manage(self.e,self.packet('.9',NOW+5),forbidden,NOW+5,True,lambda:NOW+5)
        self.assertFalse(self.e.db.execute('SELECT 1 FROM exit_orders').fetchone())
        self.assertIsNone(self.e.db.execute('SELECT triggered_at FROM probability_trails').fetchone()[0])

    def test_official_settlement_cancels_pending_exit_without_another_credit(self):
        key,p=self.buy()
        manage(self.e,self.packet('.8',NOW+5),lambda m,after=0:self.f.quotes(NOW+5),NOW+5,True,lambda:NOW+5)
        oid,wallet,key,encoded=self.e.db.execute('SELECT order_id,wallet,entry_key,payload FROM exit_orders').fetchone()
        self.f.m.update(settlement_status='VERIFIED',official_winner='UP',settled_at=iso(NOW+61),settlement_evidence='official')
        self.e.settle([self.f.m],NOW+62)
        cash=self.e.db.execute("SELECT cash FROM wallets WHERE name='Champion'").fetchone()[0]
        finish(self.e,oid,wallet,key,encoded,{},NOW+62)
        result=json.loads(self.e.db.execute('SELECT result FROM exit_orders').fetchone()[0])
        self.assertEqual(result['state'],'CANCELLED');self.assertEqual(result['fees'],'0')
        self.assertEqual(result['net_proceeds'],'0')
        self.assertEqual(self.e.db.execute("SELECT cash FROM wallets WHERE name='Champion'").fetchone()[0],cash)

    def test_stale_packet_does_not_create_or_fill_exit_and_stream_budget_expires(self):
        key,p=self.buy()
        manage(self.e,self.packet('.1',NOW+5),lambda *args:(_ for _ in ()).throw(AssertionError('No quote')),NOW+5,False,lambda:NOW+5)
        self.assertFalse(self.e.db.execute('SELECT 1 FROM exit_orders').fetchone())
        self.assertEqual(reserve_slot(self.e.db,'Champion',self.f.m,NOW+901,SETTINGS),self.f.m['market_slug']+'::entry2')

    def test_stream_quota_is_shared_and_pending_reserves_without_charging_unfilled(self):
        with self.e.db:
            for i in range(3):
                p=dict(self.f.p,asset='BTC',duration_seconds=900,opened_at=NOW-i,state='PAPER_CLOSED')
                self.e.db.execute('INSERT INTO positions VALUES(?,?,?)',('wallet'+str(i),'prior'+str(i),json.dumps(p)))
        with self.assertRaisesRegex(ValueError,'ROLLING_MARKET_ENTRY_LIMIT'): reserve_slot(self.e.db,'Champion',self.f.m,NOW,SETTINGS)
        with self.e.db: self.e.db.execute('DELETE FROM positions')
        self.e.propose('Champion',self.f.m,self.f.p,self.f.details,self.f.quotes(NOW),NOW,NOW-1)
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM positions').fetchone()[0],0)
        with self.e.db:
            for wallet in ('Challenger B','BTC_15m'):
                data=dict(plan=dict(asset='BTC',duration_seconds=900,market_slug=self.f.m['market_slug'],created_at=NOW))
                self.e.db.execute('INSERT INTO orders VALUES(?,?,?,?,NULL)',(wallet,self.f.m['market_slug'],'PROPOSED',json.dumps(data)))
        with self.assertRaisesRegex(ValueError,'ROLLING_MARKET_ENTRY_LIMIT'): reserve_slot(self.e.db,'Champion',self.f.m,NOW,SETTINGS)
        with self.e.db: self.e.db.execute("UPDATE orders SET state='REJECTED'")
        self.assertIn('::entry2',reserve_slot(self.e.db,'Champion',self.f.m,NOW+16,SETTINGS))
        self.assertEqual(self.e.db.execute("SELECT cash FROM wallets WHERE name='Champion'").fetchone()[0],'1000')

    def test_reentry_same_contract_keeps_separate_accounting_and_settles_real_slug(self):
        key,p=self.buy()
        with self.e.db:
            p.update(state='PAPER_CLOSED',payout='0',pnl='-'+p['cost'],closed_at=NOW+5)
            self.e.db.execute('UPDATE positions SET payload=?',(json.dumps(p),))
        next_p=dict(self.f.p,recorded_at=iso(NOW+15))
        self.e.propose('Champion',self.f.m,next_p,self.f.details,self.f.quotes(NOW+16),NOW+16,NOW+15)
        key2,encoded=self.e.db.execute("SELECT market_slug,payload FROM orders WHERE state='PROPOSED'").fetchone()
        self.assertNotEqual(key,key2)
        self.e.complete('Champion',key2,encoded,self.f.quotes(NOW+20),NOW+20)
        self.f.m.update(settlement_status='VERIFIED',official_winner='UP',settled_at=iso(NOW+61),settlement_evidence='official')
        self.e.settle([self.f.m],NOW+62)
        report=self.e.report(NOW+63,True)
        self.assertEqual(report['portfolios']['Champion']['account']['market_pnl'][0]['closed_trades'],2)
        self.assertTrue(all(json.loads(r[0])['market_slug']==self.f.m['market_slug'] for r in self.e.db.execute('SELECT payload FROM positions')))

if __name__=='__main__': unittest.main()
