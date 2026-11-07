from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import json
import copy
import sqlite3
import tempfile
import unittest
from trading_bot.core import amount
from trading_bot.observed_paper import Engine
from trading_bot.provider import directional_book,mapping,corroboration
from trading_bot.tests.test_execution_audit import metadata,book,market,NOW,iso


class ObservedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'new.sqlite';self.engine=Engine(self.path)
        self.m=market();self.m.update(window_start=iso(NOW-840),window_end=iso(NOW+60),settlement_status='PENDING')
        self.details=metadata()['market'];self.details['assetPriceTerms'].update(windowStart=self.m['window_start'],windowEnd=self.m['window_end'])
        self.details.update(description='This market will settle to Up if the price is greater than or equal to the starting price. Otherwise, this market will settle to Down.',orderPriceMinTickSize='.01',minimumTradeQty='.01')
        for side in self.details['marketSides']: side.update(identifier='exact-contract',tradable=True)
        self.proof=dict(total=4,UP=2,DOWN=2,conflicts=0)
        self.p=dict(market_slug=self.m['market_slug'],recorded_at=iso(NOW-5),model_version='Pixel V13.5 Headless Baseline',predicted_up_probability='.9')

    def tearDown(self): self.engine.close();self.tmp.cleanup()

    def quotes(self,now):
        raw=book()
        raw['marketData']['bids'][0]['qty']='100'
        raw['marketData']['offers'][0]['qty']='100'
        return directional_book(self.m,self.details,self.proof,raw,now-1,now)

    def test_exported_evidence_is_distinct_read_only_and_conflicts_are_not_hidden(self):
        from trading_bot.provider import evidence_packet
        source=Path(self.tmp.name)/'collector.sqlite'
        with sqlite3.connect(source) as db:
            db.execute('CREATE TABLE evidence(market_slug TEXT,observed_at TEXT,payload TEXT)')
            for index,up in enumerate((True,False,True)):
                d=copy.deepcopy(self.details)
                d.update(slug='resolved'+str(index),closed=True,status='MARKET_STATUS_RESOLVED')
                d['assetPriceTerms'].update(horizon='15m',settlementPrice=dict(value='76000' if up else '74000',currency='USD'))
                for side in d['marketSides']: side['price']=str(int(up==side['long']))
                for t in (1,2): db.execute('INSERT INTO evidence VALUES(?,?,?)',(d['slug'],iso(NOW-t),json.dumps(d)))
            db.execute('INSERT INTO evidence VALUES(?,?,?)',(self.m['market_slug'],iso(NOW),json.dumps(self.details)))
        before=source.read_bytes()
        packet=evidence_packet(source)
        self.assertEqual(packet['proofs']['BTC_15m'],dict(total=3,UP=2,DOWN=1,conflicts=0))
        self.assertEqual(set(packet['metadata']),{self.m['market_slug']})
        self.assertEqual(source.read_bytes(),before)

    def test_direction_mapping_requires_typed_semantics_and_independent_proof(self):
        q=self.quotes(NOW)
        self.assertEqual(q['DOWN']['offers'][0]['price'],'0.40')
        self.assertEqual(q['DOWN']['intent'],'ORDER_INTENT_BUY_SHORT')
        with self.assertRaisesRegex(ValueError,'CORROBORATION'):
            mapping(self.m,self.details,dict(total=30,UP=30,DOWN=0))
        with self.assertRaisesRegex(ValueError,'SIDE_IDENTITY'):
            self.details['marketSides'][0]['long']=False
            mapping(self.m,self.details,self.proof)

    def test_proposal_is_not_a_fill_then_delay_fill_and_settle_exactly_once(self):
        self.engine.propose('Champion',self.m,self.p,self.details,self.quotes(NOW),NOW,NOW-1)
        payload=self.engine.db.execute('SELECT payload FROM orders').fetchone()[0]
        self.assertEqual(self.engine.report(NOW,True)['portfolios']['Champion']['account']['cash'],'1000')
        self.engine.complete('Champion',self.m['market_slug'],payload,self.quotes(NOW),NOW+1)
        self.assertFalse(self.engine.db.execute('SELECT 1 FROM positions').fetchone())
        self.engine.complete('Champion',self.m['market_slug'],payload,self.quotes(NOW+4),NOW+4)
        account=self.engine.report(NOW+4,True)['portfolios']['Champion']['account']
        self.assertEqual(len(account['positions']),1)
        self.assertEqual(account['positions'][0]['price_basis'],'OBSERVED_POST_DELAY_BOOK')
        self.assertNotEqual(account['positions'][0]['entry_price'],'.50')
        cash=account['cash'];self.engine.complete('Champion',self.m['market_slug'],payload,self.quotes(NOW+4),NOW+4)
        self.assertEqual(self.engine.report(NOW+4,True)['portfolios']['Champion']['account']['cash'],cash)
        self.m.update(settlement_status='VERIFIED',official_winner='UP',settled_at=iso(NOW+61),settlement_evidence='official typed prices')
        self.engine.settle([self.m],NOW+62)
        closed=self.engine.report(NOW+62,True)['portfolios']['Champion']['account']
        self.engine.settle([self.m],NOW+63)
        self.assertEqual(self.engine.report(NOW+63,True)['portfolios']['Champion']['account']['cash'],closed['cash'])
        self.assertGreater(Decimal(closed['realized_pnl']),0)
        self.assertEqual(closed['market_pnl'][0]['closed_trades'],1)

    def test_restart_reservation_expiry_and_pause_never_charge_fee(self):
        self.engine.propose('Champion',self.m,self.p,self.details,self.quotes(NOW),NOW,NOW-1)
        self.assertEqual(self.engine.risk('Champion',NOW),0)
        self.engine.close();self.engine=Engine(self.path)
        payload=self.engine.db.execute('SELECT payload FROM orders').fetchone()[0]
        self.engine.complete('Champion',self.m['market_slug'],payload,{},NOW+16)
        report=self.engine.report(NOW+16,True)['portfolios']['Champion']
        self.assertEqual(report['account']['cash'],'1000')
        self.assertEqual(report['order_states']['REJECTED'],1)
        self.assertFalse(report['account']['positions'])

    def test_foreign_target_does_not_settle_and_fee_sensitivity_is_separate(self):
        self.details['feeCoefficient']='.095'
        self.engine.propose('Champion',self.m,self.p,self.details,self.quotes(NOW),NOW,NOW-1)
        payload=self.engine.db.execute('SELECT payload FROM orders').fetchone()[0]
        self.engine.complete('Champion',self.m['market_slug'],payload,self.quotes(NOW+4),NOW+4)
        p=self.engine.report(NOW+4,True)['portfolios']['Champion']['account']['positions'][0]
        self.assertGreater(amount(p['fees_at_api_coefficient']),amount(p['fees']))
        self.m.update(settlement_status='VERIFIED',official_winner='UP',settled_at=iso(NOW+61),settlement_evidence='official',official_price_to_beat='123')
        self.engine.settle([self.m],NOW+62)
        self.assertEqual(self.engine.report(NOW+62,True)['portfolios']['Champion']['account']['positions'][0]['state'],'PAPER_OPEN')

if __name__=='__main__': unittest.main()
