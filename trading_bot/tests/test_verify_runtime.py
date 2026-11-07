from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from trading_bot.verify_runtime import reconcile,pbot_report,cbot_report
from trading_bot.observed_paper import Engine
from coinbase_bot.observed import ObservedBot

class VerifyTests(unittest.TestCase):
    def test_open_cost_and_closed_pnl_must_reconcile_without_counting_reservations_as_spent(self):
        positions=[dict(state='PAPER_OPEN',cost='10')]
        self.assertTrue(reconcile('992',positions,[dict(pnl='2')])['accounting_ok'])
        self.assertFalse(reconcile('991',positions,[dict(pnl='2')])['accounting_ok'])

    def test_diagnostics_read_both_new_ledgers_without_mutating_them(self):
        with tempfile.TemporaryDirectory() as folder:
            p,c=Path(folder)/'p.sqlite',Path(folder)/'c.sqlite'
            pbot=Engine(p);pbot.report(100,True);pbot.close()
            cbot=ObservedBot(c);cbot.cycle({},100);cbot.close()
            before=(p.read_bytes(),c.read_bytes())
            report=pbot_report(p,101)
            self.assertTrue(all(w['accounting_ok'] for w in report['wallets']))
            self.assertFalse(report['live_orders_enabled'])
            report=cbot_report(c,101)
            self.assertTrue(report['accounting_ok'])
            self.assertEqual((p.read_bytes(),c.read_bytes()),before)

if __name__=='__main__': unittest.main()
