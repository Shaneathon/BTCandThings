from decimal import Decimal
import unittest
from coinbase_bot.review import trade_metrics,aggregate

class ReviewTests(unittest.TestCase):
    def test_fee_drag_can_turn_a_positive_move_into_a_loss(self):
        trade=dict(product_id='BTC-USD',quantity='1',entry_price='100',exit_price='101',cost='100.6',
                   proceeds='100.394',pnl='-0.206',entry_fees='.6',exit_fees='.606',opened_at=0,closed_at=120,exit_reason='TREND_EXIT')
        row=trade_metrics(trade);summary=aggregate([row])
        self.assertEqual(row['gross'],Decimal(1))
        self.assertEqual(summary['estimated_fees'],'1.206')
        self.assertEqual(summary['net_pnl'],'-0.206')
        self.assertEqual(summary['gross_positive_but_net_nonpositive'],1)
        self.assertEqual(summary['median_hold_minutes'],2)
        with self.assertRaisesRegex(ValueError,'RECONCILE'): trade_metrics(dict(trade,pnl='1'))
        self.assertEqual(aggregate([])['closed_trades'],0)

if __name__=='__main__': unittest.main()
