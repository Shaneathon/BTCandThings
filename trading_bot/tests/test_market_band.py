from decimal import Decimal
from pathlib import Path
import copy,json,tempfile,unittest
from trading_bot.band_runner import Engine
from trading_bot.observed_paper import Engine as LegacyEngine,SETTINGS as LEGACY_POLICY
from trading_bot.market_band import BAND_SETTINGS,observe_lean,entry_check,update_exit
from trading_bot.entry_policy import phase,reserve_slot
from trading_bot.entry_limits import migrate
from trading_bot.paper_exits import manage,finish
from trading_bot.provider import directional_book
from trading_bot.tests.test_execution_audit import NOW,iso,market,metadata,book
from trading_bot.dual_sandbox import RESEARCH_MODEL

class BandTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'paper.sqlite';self.engine=Engine(self.path)
        self.m=dict(market(),window_start=iso(NOW-300),window_end=iso(NOW+600),settlement_status='PENDING')
        self.details=metadata()['market'];self.details['assetPriceTerms'].update(windowStart=self.m['window_start'],windowEnd=self.m['window_end'])
        self.details.update(description='This market will settle to Up if the price is greater than or equal to the starting price. Otherwise, this market will settle to Down.',orderPriceMinTickSize='.01',minimumTradeQty='.01')
        for s in self.details['marketSides']: s.update(identifier=self.m['contract_slug'],tradable=True)
        self.proof=dict(total=4,UP=2,DOWN=2,conflicts=0)
        self.forecast=dict(market_slug=self.m['market_slug'],model_version='Pixel V13.5 Headless Baseline',recorded_at=iso(NOW-2),predicted_up_probability='.9')
        self.lean('UP',NOW)
    def tearDown(self): self.engine.close();self.tmp.cleanup()
    def lean(self,direction,now,**changes):
        p=dict(market_slug=self.m['market_slug'],model_version=RESEARCH_MODEL,recorded_at=iso(now-2),source_timestamp=iso(now-10),
            lean_direction=direction,predicted_up_probability='.6',feature_snapshot=dict(asset='BTC',duration_seconds=900,target='75000'))
        p.update(changes)
        data=dict(exported_at=now-1,predictions=[p]);observe_lean(self.engine.db,self.m,data,now)
        return data
    def quotes(self,now,up='.60'):
        px=Decimal(up);raw=book();raw['marketData']['bids'][0].update(px=dict(value=str(px-Decimal('.01')),currency='USD'),qty='100')
        raw['marketData']['offers'][0].update(px=dict(value=str(px+Decimal('.01')),currency='USD'),qty='100')
        raw['marketData']['stats']=dict(currentPx=dict(value=str(px),currency='USD'))
        return directional_book(self.m,self.details,self.proof,raw,now-1,now)
    def buy(self,up='.60'):
        self.engine.propose('Champion',self.m,self.forecast,self.details,self.quotes(NOW,up),NOW,NOW-1)
        key,encoded=self.engine.db.execute("SELECT market_slug,payload FROM orders WHERE state='PROPOSED'").fetchone()
        self.engine.complete('Champion',key,encoded,self.quotes(NOW+4,up),NOW+4)
        p=json.loads(self.engine.db.execute('SELECT payload FROM positions WHERE market_slug=?',(key,)).fetchone()[0])
        return key,p
    def test_market_mark_not_model_or_last_trade_selects_entry(self):
        self.forecast['predicted_up_probability']='.1'
        key,p=self.buy()
        self.assertEqual(p['side'],'UP');self.assertEqual(p['entry_market_probability'],'0.60')
        self.assertLessEqual(Decimal(p['cost']),Decimal('1.50'))
        self.assertEqual(p['entry_market_source'],'marketData.stats.currentPx')
    def test_band_boundaries_and_down_favorite_require_same_lean(self):
        for px in ('.54','.64'):
            self.assertEqual(entry_check(self.engine.db,self.m,self.quotes(NOW,px),NOW,BAND_SETTINGS)['side'],'UP')
        for px in ('.53','.65','.50'):
            with self.assertRaisesRegex(ValueError,'OUTSIDE'): entry_check(self.engine.db,self.m,self.quotes(NOW,px),NOW,BAND_SETTINGS)
        self.lean('DOWN',NOW)
        self.assertEqual(entry_check(self.engine.db,self.m,self.quotes(NOW,'.4'),NOW,BAND_SETTINGS)['side'],'DOWN')
        with self.assertRaisesRegex(ValueError,'LEAN_NOT_ALIGNED'): entry_check(self.engine.db,self.m,self.quotes(NOW),NOW,BAND_SETTINGS)
    def test_neutral_stale_missing_wrong_target_leans_never_enter(self):
        for direction,changes in [('NEUTRAL',{}),('UP',dict(recorded_at=iso(NOW-100))),('UP',dict(feature_snapshot=dict(asset='BTC',duration_seconds=900,target='1')))]:
            self.lean(direction,NOW,**changes)
            with self.assertRaises(ValueError): entry_check(self.engine.db,self.m,self.quotes(NOW),NOW,BAND_SETTINGS)
        with self.engine.db: self.engine.db.execute('DELETE FROM current_market_lean')
        with self.assertRaisesRegex(ValueError,'NO_FRESH'): entry_check(self.engine.db,self.m,self.quotes(NOW),NOW,BAND_SETTINGS)
    def test_no_mark_no_fallback_and_stale_mark_blocked(self):
        q=self.quotes(NOW);q['UP']['market_up_probability']=None
        with self.assertRaisesRegex(ValueError,'NO_CURRENT'): entry_check(self.engine.db,self.m,q,NOW,BAND_SETTINGS)
        with self.assertRaisesRegex(ValueError,'STALE_MARKET'): entry_check(self.engine.db,self.m,self.quotes(NOW-6),NOW,BAND_SETTINGS)
    def test_wide_spread_and_unknown_target_policy_are_rejected(self):
        q=self.quotes(NOW);q['UP']['liquidation_bids'][0]['price']='.40'
        with self.assertRaisesRegex(ValueError,'SPREAD_TOO_WIDE'): entry_check(self.engine.db,self.m,q,NOW,BAND_SETTINGS)
        with self.assertRaisesRegex(ValueError,'Unreviewed target'): migrate(self.path,target_settings=dict(version='UNKNOWN'))
        self.assertEqual(json.loads(self.engine.db.execute('SELECT payload FROM settings').fetchone()[0]),BAND_SETTINGS)

    def test_wait_and_distinct_five_fifteen_minute_cutoffs(self):
        for duration,cutoff in ((900,180),(300,120)):
            m=dict(self.m,duration_seconds=duration,window_start=iso(NOW-89),window_end=iso(NOW-89+duration))
            with self.assertRaisesRegex(ValueError,'OPENING_WAIT'): phase(self.engine.db,'Champion',m,self.forecast,NOW,BAND_SETTINGS)
            m.update(window_start=iso(NOW-90),window_end=iso(NOW-90+duration))
            self.assertEqual(phase(self.engine.db,'Champion',m,self.forecast,NOW,BAND_SETTINGS)['phase'],'MARKET_BAND')
            m.update(window_start=iso(NOW-(duration-cutoff)),window_end=iso(NOW+cutoff))
            with self.assertRaisesRegex(ValueError,'ENTRY_CUTOFF'): phase(self.engine.db,'Champion',m,self.forecast,NOW,BAND_SETTINGS)
    def test_delay_rechecks_band_lean_cutoff_and_price_limit(self):
        self.engine.propose('Champion',self.m,self.forecast,self.details,self.quotes(NOW),NOW,NOW-1)
        key,encoded=self.engine.db.execute('SELECT market_slug,payload FROM orders').fetchone()
        self.engine.complete('Champion',key,encoded,self.quotes(NOW+4,'.65'),NOW+4)
        self.assertFalse(self.engine.db.execute('SELECT 1 FROM positions').fetchone())
        self.assertEqual(self.engine.db.execute("SELECT cash FROM wallets WHERE name='Champion'").fetchone()[0],'1000')
    def test_lean_flip_during_delay_cancels_without_spending(self):
        self.engine.propose('Champion',self.m,self.forecast,self.details,self.quotes(NOW),NOW,NOW-1)
        key,encoded=self.engine.db.execute('SELECT market_slug,payload FROM orders').fetchone()
        self.lean('DOWN',NOW+4)
        self.engine.complete('Champion',key,encoded,self.quotes(NOW+4),NOW+4)
        self.assertFalse(self.engine.db.execute('SELECT 1 FROM positions').fetchone())
        self.assertEqual(json.loads(self.engine.db.execute('SELECT result FROM orders').fetchone()[0])['reason'],'LEAN_NOT_ALIGNED_WITH_MARKET_FAVORITE')

    def test_cycle_ingests_changed_lean_before_processing_pending_entry(self):
        from trading_bot.observed_paper import cycle
        self.engine.propose('Champion',self.m,self.forecast,self.details,self.quotes(NOW),NOW,NOW-1)
        # Build a packet carrying a new DOWN lean; leave the database UP until cycle.
        data=self.lean('DOWN',NOW+4)
        self.lean('UP',NOW)
        data.update(markets=[self.m],execution_evidence=dict(metadata={self.m['market_slug']:self.details},proofs={}))
        data['predictions'].append(self.forecast)
        fixture=self
        class Client:
            def load(self,*args): return fixture.quotes(NOW+4)
        cycle(self.engine,data,Client(),NOW+4)
        self.assertFalse(self.engine.db.execute('SELECT 1 FROM positions').fetchone())
        self.assertEqual(self.engine.db.execute("SELECT cash FROM wallets WHERE name='Champion'").fetchone()[0],'1000')

    def test_stop_is_fixed_entry_minus_two_not_trailing_and_profit_is_71(self):
        key,p=self.buy('.55')
        for up in ('.70','.60','.54'):
            state=update_exit(self.engine,'Champion',key,p,self.quotes(NOW+5,up),NOW+5)
            self.assertIsNone(state['triggered_at'])
            self.assertEqual(Decimal(state['stop_probability']),Decimal('.53'))
        state=update_exit(self.engine,'Champion',key,p,self.quotes(NOW+6,'.53'),NOW+6)
        self.assertEqual(state['reason'],'MARKET_ENTRY_MINUS_2_POINTS')
        state=update_exit(self.engine,'Champion',key,p,self.quotes(NOW+7,'.71'),NOW+7)
        self.assertEqual(state['reason'],'MARKET_ENTRY_MINUS_2_POINTS') # latched first trigger
    def test_already_triggered_exit_does_not_wait_for_a_new_mark(self):
        key,p=self.buy('.55')
        update_exit(self.engine,'Champion',key,p,self.quotes(NOW+5,'.53'),NOW+5)
        q=self.quotes(NOW+6,'.52');q['UP']['market_up_probability']=None
        state=update_exit(self.engine,'Champion',key,p,q,NOW+6)
        self.assertEqual(state['reason'],'MARKET_ENTRY_MINUS_2_POINTS')
        self.assertEqual(state['triggered_at'],NOW+5)

    def test_down_exit_uses_complement_and_sell_uses_actual_bid_with_fees(self):
        self.lean('DOWN',NOW);key,p=self.buy('.40')
        state=update_exit(self.engine,'Champion',key,p,self.quotes(NOW+5,'.29'),NOW+5)
        self.assertEqual(state['reason'],'MARKET_71_PERCENT_TARGET')
        data=dict(exported_at=NOW+5,markets=[self.m],predictions=[],execution_evidence=dict(metadata={self.m['market_slug']:self.details}))
        manage(self.engine,data,lambda m,after=0:self.quotes(NOW+5,'.29'),NOW+5,True,lambda:NOW+5)
        oid,wallet,key,encoded=self.engine.db.execute('SELECT order_id,wallet,entry_key,payload FROM exit_orders').fetchone()
        finish(self.engine,oid,wallet,key,encoded,self.quotes(NOW+8,'.29'),NOW+8)
        closed=json.loads(self.engine.db.execute('SELECT payload FROM positions').fetchone()[0])
        self.assertEqual(closed['close_reason'],'MARKET_71_PERCENT_TARGET')
        self.assertEqual(Decimal(closed['exit_price']),Decimal('.70'))
        self.assertGreater(Decimal(closed['exit_fees']),0)
        self.assertEqual(Decimal(closed['payout'])-Decimal(closed['cost']),Decimal(closed['pnl']))
    def test_five_entry_rolling_cap_is_shared_and_source_collection_not_changed(self):
        with self.engine.db:
            for i in range(5):
                p=dict(asset='BTC',duration_seconds=900,opened_at=NOW-i)
                self.engine.db.execute('INSERT INTO positions VALUES(?,?,?)',('wallet'+str(i),'prior'+str(i),json.dumps(p)))
        with self.assertRaisesRegex(ValueError,'ROLLING'): reserve_slot(self.engine.db,'Champion',self.m,NOW,BAND_SETTINGS)
        self.assertEqual(BAND_SETTINGS['max_entries_per_stream'],5)
        from trading_bot.dual_sandbox import MARKET_STREAMS
        self.assertEqual(len(MARKET_STREAMS),8)
    def test_known_prior_migration_idempotence_and_rollback_preserve_wallets(self):
        self.engine.close()
        with __import__('sqlite3').connect(self.path) as db: db.execute('UPDATE settings SET payload=?',(json.dumps(LEGACY_POLICY,sort_keys=True),))
        self.assertTrue(migrate(self.path,target_settings=BAND_SETTINGS)['policy_changed'])
        self.assertFalse(migrate(self.path,target_settings=BAND_SETTINGS)['policy_changed'])
        self.assertTrue(migrate(self.path,rollback=True,target_settings=BAND_SETTINGS)['policy_changed'])
        self.engine=LegacyEngine(self.path)
        self.assertEqual(self.engine.db.execute('SELECT cash FROM wallets LIMIT 1').fetchone()[0],'1000')

if __name__=='__main__': unittest.main()
