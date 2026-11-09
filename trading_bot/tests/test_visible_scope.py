import unittest
from copy import deepcopy
from trading_bot.visible_scope import focused_snapshot,BTC15_WALLETS

class VisibleScopeTests(unittest.TestCase):
    def test_only_three_wallets_no_cached_or_financial_mutation(self):
        names=BTC15_WALLETS+('ETH_5m','SOL_15m')
        data=dict(portfolios={n:dict(account=dict(cash='999'),activity=dict(last_filled_at=i)) for i,n in enumerate(names)},automatic_review=dict(wallets=[dict(wallet=n) for n in names]),display_health=dict(last_filled_at=99))
        original=deepcopy(data);view=focused_snapshot(data,True)
        self.assertEqual(set(view['portfolios']),set(BTC15_WALLETS))
        self.assertEqual(view['display_health']['last_filled_at'],2)
        self.assertEqual(len(view['automatic_review']['wallets']),3)
        self.assertEqual(data,original)
        self.assertEqual(view['portfolios']['Champion']['account']['cash'],'999')
    def test_default_view_unchanged(self):
        data=dict(portfolios={'ETH_5m':{}})
        self.assertEqual(focused_snapshot(data),data)
