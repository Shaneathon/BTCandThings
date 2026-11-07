from datetime import datetime
import copy
import json
from pathlib import Path
import tempfile
import unittest
from trading_bot.display_status import central,enrich,wallet_state
from trading_bot.observed_paper import Engine

NOW=datetime.fromisoformat('2026-11-07T13:08:46+00:00').timestamp()

class DisplayTests(unittest.TestCase):
    def test_central_time_dates_and_daylight_saving_are_correct(self):
        self.assertIn('07:08:46 AM CST',central(NOW))
        summer=datetime.fromisoformat('2026-07-01T13:00:00+00:00').timestamp()
        self.assertIn('08:00:00 AM CDT',central(summer))
        self.assertEqual(central(None),'None yet')

    def test_read_only_details_use_all_fills_not_truncated_position_table(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledger=root/'observed.sqlite';packet=root/'input.json'
            engine=Engine(ledger)
            for i in range(40):
                position=dict(market_slug='history'+str(i),asset='BTC',duration_seconds=900,model_version='fixture',state='PAPER_CLOSED',opened_at=NOW-100-i,closed_at=NOW-80-i,cost='1',pnl='0',fees='0',payout='1')
                engine.db.execute('INSERT INTO positions VALUES(?,?,?)',('Champion','history'+str(i),json.dumps(position)))
            position=dict(market_slug='a-hidden-newest',asset='BTC',duration_seconds=900,model_version='fixture',state='PAPER_CLOSED',opened_at=NOW-2,closed_at=NOW-1,cost='1',pnl='0',fees='0',payout='1')
            engine.db.execute('INSERT INTO positions VALUES(?,?,?)',('Champion','a-hidden-newest',json.dumps(position)))
            engine.db.commit()
            report=engine.report(NOW,True);engine.close()
            report['portfolios']['Champion']['account']['positions']=[]
            packet.write_text(json.dumps(dict(exported_at=NOW-1,markets=[],predictions=[])))
            before=ledger.read_bytes()
            result=enrich(ledger,report,NOW,packet)
            a=result['portfolios']['Champion']['activity']
            self.assertEqual(a['last_filled_at'],NOW-2)
            self.assertEqual(a['last_settled_at'],NOW-1)
            self.assertEqual(a['filled_trade_count'],41)
            self.assertTrue(result['display_health']['input_fresh'])
            self.assertEqual(ledger.read_bytes(),before)

    def test_coinbase_status_is_not_enriched_as_polymarket(self):
        from coinbase_bot.observed import ObservedBot
        from trading_bot.server import snapshot
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'coinbase.sqlite'
            bot=ObservedBot(path);bot.cycle({},NOW);bot.close()
            result=snapshot(path)
            self.assertEqual(result['account']['venue'],'Coinbase Advanced')
            self.assertNotIn('display_health',result)

    def test_waiting_and_frozen_states_are_separate(self):
        report=dict(account=dict(halted_reason=None,market_pnl=[dict(asset='BTC',duration_seconds=900)]),
                    activity=dict(pending_orders=[],open_windows=[],risk_capacity='10'),model_version='model')
        packet=dict(markets=[dict(market_slug='current',asset='BTC',duration_seconds=900,
                                 window_start='2026-11-07T13:00:00+00:00',window_end='2026-11-07T13:15:00+00:00')])
        health=dict(engine_age_seconds=1,input_error=None,input_fresh=True)
        self.assertEqual(wallet_state(report,packet,health,NOW)['state'],'WAITING_FOR_ENTRY_WINDOW')
        health['input_fresh']=False
        self.assertEqual(wallet_state(report,packet,health,NOW)['state'],'INPUT_BLOCKED')
        health.update(input_fresh=True,engine_age_seconds=100)
        self.assertEqual(wallet_state(report,packet,health,NOW)['state'],'ENGINE_STALE')

if __name__=='__main__': unittest.main()
