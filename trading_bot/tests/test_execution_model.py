from dataclasses import replace
import unittest
from trading_bot.execution_model import OrderPlan, exchange_order, simulate, taker_fee, QUADRATIC_TAKER_RULE
from trading_bot.market_pnl import summarize


def plan():
    # Explicit synthetic flat fee for tests. Not Polymarket's observed .095.
    return OrderPlan('event','contract','test','BTC',900,'UP','ORDER_INTENT_BUY_LONG',
        '10','.60','.01','1',100,99,102,110,120,'TIME_IN_FORCE_FILL_OR_KILL',
        'test-only mapping','VERIFIED_FLAT_PER_SHARE','.01','synthetic fee fixture')


def book():
    return dict(market_slug='event',contract_slug='contract',side='UP',intent='ORDER_INTENT_BUY_LONG',
                mapping_evidence='test-only mapping',approved=True,request_started_at=102,received_at=103,
                offers=[dict(price='.55',quantity='20'),dict(price='.60',quantity='20'),dict(price='.70',quantity='100')])


class ExecutionTests(unittest.TestCase):
    def test_shared_order_and_depth_weighted_costs(self):
        result=simulate(plan(),book(),103)
        self.assertEqual(result['order'],exchange_order(plan()))
        self.assertEqual(result['state'],'FILLED')
        self.assertEqual(result['filled_quantity'],'10')
        self.assertEqual(result['gross_cost'],'5.75')
        self.assertEqual(result['fees'],'0.10')
        self.assertEqual(result['total_cost'],'5.85')
        self.assertFalse(result['live_orders_enabled'])

    def test_partial_ioc_versus_atomic_fok(self):
        data=book();data['offers']=data['offers'][:1]
        fok=simulate(plan(),data,103)
        self.assertEqual(fok['state'],'REJECTED')
        self.assertEqual(fok['filled_quantity'],'0')
        ioc=simulate(replace(plan(),time_in_force='TIME_IN_FORCE_IMMEDIATE_OR_CANCEL'),data,103)
        self.assertEqual(ioc['state'],'PARTIALLY_FILLED_CANCELLED')
        self.assertEqual(ioc['filled_quantity'],'5')

    def test_prior_quote_expiry_wrong_identity_and_unknown_fees_do_not_fill(self):
        for change in [dict(request_started_at=101),dict(received_at=112),dict(contract_slug='other'),
                       dict(approved=False),dict(side='DOWN')]:
            data=book();data.update(change)
            self.assertEqual(simulate(plan(),data,103)['state'],'REJECTED')
        self.assertEqual(simulate(plan(),book(),111)['state'],'REJECTED')
        with self.assertRaisesRegex(ValueError,'FEE_RULE'):
            simulate(replace(plan(),fee_rule='ASSUME_COEFFICIENT_TIMES_PRICE',fee_parameter='.095'),book(),103)

    def test_rounding_and_order_identity_are_immutable(self):
        with self.assertRaises(ValueError):
            exchange_order(replace(plan(),limit_price='.605'))
        self.assertNotEqual(plan().order_id,replace(plan(),quantity='11').order_id)
        self.assertEqual(plan().order_id,plan().order_id)
        data=book();data['offers'].append(data['offers'][0])
        self.assertEqual(simulate(plan(),data,103)['state'],'REJECTED')

    def test_quadratic_fees_bankers_rounding_per_execution(self):
        self.assertEqual(str(taker_fee('.06','100','.50')),'1.50')
        self.assertEqual(str(taker_fee('.095','100','.50')),'2.38')
        self.assertEqual(str(taker_fee('.02','1','.50')),'0.00')
        self.assertEqual(str(taker_fee('.06','1','.50')),'0.02')
        self.assertNotEqual(sum(taker_fee('.02','1','.5') for _ in range(3)),taker_fee('.02','3','.5'))
        for coefficient,qty,price in [('.06','1','NaN'),('.06','-1','.5'),('.06','1','.001')]:
            with self.assertRaises((ValueError,ArithmeticError)):
                taker_fee(coefficient,qty,price)
        configured=replace(plan(),fee_rule=QUADRATIC_TAKER_RULE,fee_parameter='.06',
                           fee_evidence='Synthetic support-formula test; not market coefficient approval')
        result=simulate(configured,book(),103)
        self.assertEqual(result['fees'],'0.14')
        self.assertEqual(result['total_cost'],'5.89')
        self.assertFalse(result['actual_exchange_fill_partition_known'])
        empty=book();empty['offers']=empty['offers'][:1]
        self.assertEqual(simulate(configured,empty,103)['fees'],'0')

    def test_market_accounting_reconciles_gross_fees_net_and_open_cost(self):
        positions=[dict(market_slug='btc1',asset='BTC',duration_seconds=900,state='PAPER_CLOSED',
                        cost='6',fees='1',payout='10',pnl='4'),
                   dict(market_slug='eth1',asset='ETH',duration_seconds=300,state='PAPER_CLOSED',
                        cost='6',fees='1',payout='0',pnl='-6'),
                   dict(market_slug='btc2',asset='BTC',duration_seconds=900,state='PAPER_OPEN',cost='3')]
        rows=summarize(positions)
        self.assertEqual(rows[0]['realized_gross_pnl'],'5')
        self.assertEqual(rows[0]['entry_fees'],'1')
        self.assertEqual(rows[0]['realized_net_pnl'],'4')
        self.assertEqual(rows[0]['open_cost'],'3')
        self.assertEqual(rows[1]['realized_net_pnl'],'-6')
        with self.assertRaisesRegex(ValueError,'reconcile'):
            summarize([dict(positions[0],pnl='5')])
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            summarize([positions[0],positions[0]])

if __name__=='__main__':
    unittest.main()
