import copy
from decimal import Decimal
import unittest
from trading_bot.performance_periods import CURRENT,breakdown,period


class PeriodTests(unittest.TestCase):
    def test_policy_provenance_not_cost_or_settlement_time_controls_membership(self):
        old=dict(market_slug='old',asset='BTC',duration_seconds=300,state='PAPER_CLOSED',pnl='-1',cost='1',fees='.02',payout='0')
        new=dict(old,market_slug='new',pnl='1.75',cost='.25',payout='2',entry_limits=dict(version=CURRENT))
        opened=dict(new,market_slug='open',state='PAPER_OPEN',cost='2')
        rows=[old,new,opened];before=copy.deepcopy(rows)
        result=breakdown(rows,streams=[('BTC',300)])
        self.assertEqual(period(old),'earlier')  # An old $1 entry is still old.
        self.assertEqual(period(new),'current') # A current 25-cent partial is current.
        self.assertEqual(result['current']['realized_pnl'],'1.75')
        self.assertEqual(result['earlier']['realized_pnl'],'-1')
        self.assertEqual(result['current']['filled_trades'],2)
        self.assertEqual(result['current']['open_cost'],'2')
        self.assertEqual(Decimal(result['all']['realized_pnl']),Decimal(result['current']['realized_pnl'])+Decimal(result['earlier']['realized_pnl']))
        self.assertEqual(rows,before)

if __name__=='__main__': unittest.main()
