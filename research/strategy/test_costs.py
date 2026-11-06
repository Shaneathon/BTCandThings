from decimal import Decimal
import unittest
from costs import binary_ev,spot_break_even_move


class CostTests(unittest.TestCase):
    def test_high_accuracy_can_have_negative_value(self):
        result=binary_ev('.95','.98','.01','.01')
        self.assertEqual(result['expected_net_per_share'],Decimal('-.05'))
        self.assertEqual(binary_ev('.60','.50','.01','.01')['expected_net_per_share'],Decimal('.08'))

    def test_spot_hurdle_matches_roundtrip_cashflows(self):
        hurdle=spot_break_even_move('.006','.006','.0005','.0005')
        entry=Decimal(100)*(1+Decimal('.0005'))*(1+Decimal('.006'))
        exit_cash=Decimal(100)*(1+hurdle)*(1-Decimal('.0005'))*(1-Decimal('.006'))
        self.assertAlmostEqual(entry,exit_cash,places=20)
        self.assertEqual(spot_break_even_move(0,0,0,0),0)

    def test_invalid_inputs_rejected(self):
        for p in ('NaN','Infinity','-0.1','1.1',True):
            with self.assertRaises(ValueError): binary_ev(p,'.5',0,0)
        for rate in ('1','-1','NaN'):
            with self.assertRaises(ValueError): spot_break_even_move(rate,0,0,0)
