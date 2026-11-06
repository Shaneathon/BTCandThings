from dataclasses import replace
import json
import io
import sqlite3
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from pathlib import Path
import tempfile
import unittest
from trading_bot.dual_sandbox import MODELS, Sandbox, SandboxConfig, run_cycle, export
from trading_bot.tests.test_bot import iso

NOW=1793988840  # final minute of a BTC 15m window


def fixture(now=NOW):
    start=int(now)//900*900
    market=dict(market_slug='btc-updown-15m-test',asset='BTC',duration_seconds=900,
        window_start=iso(start),window_end=iso(start+900),contract_slug='exact-contract',
        official_price_to_beat='100',settlement_status='PENDING')
    predictions=[dict(market_slug=market['market_slug'],recorded_at=iso(now-5),
                     model_version=model,predicted_up_probability=p)
                 for model,p in zip(MODELS.values(),(.8,.2))]
    return dict(exported_at=now-1,markets=[market],predictions=predictions)


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.bots={name:Sandbox(Path(self.tmp.name)/(name+'.sqlite'),SandboxConfig(model_version=model))
                   for name,model in MODELS.items()}

    def tearDown(self):
        for bot in self.bots.values(): bot.close()
        self.tmp.cleanup()

    def test_two_independent_forward_wallets_and_exact_once_settlement(self):
        data=fixture()
        report=run_cycle(self.bots,data,NOW)
        self.assertEqual(report['common_signal_markets'],1)
        for portfolio in report['portfolios'].values():
            self.assertEqual(portfolio['account']['cash'],'990.12')
            self.assertEqual(len(portfolio['account']['positions']),1)
            position=portfolio['account']['positions'][0]
            self.assertEqual(position['price_basis'],'HYPOTHETICAL_FIXED_50C')
            self.assertFalse(position['liquidity_verified'])
            self.assertFalse(portfolio['account']['live_orders_enabled'])
        run_cycle(self.bots,data,NOW+1)
        data['markets'][0].update(settlement_status='VERIFIED',official_winner='UP',
                                 settled_at=iso(NOW+61),settlement_evidence='Official typed settlement prices')
        report=run_cycle(self.bots,data,NOW+62)
        self.assertEqual(report['portfolios']['Champion']['account']['realized_pnl'],'9.12')
        self.assertEqual(report['portfolios']['Challenger B']['account']['realized_pnl'],'-9.88')
        self.assertEqual(report['automatic_reviews']['Challenger B']['losses'],1)
        again=run_cycle(self.bots,data,NOW+63)
        self.assertEqual(again['portfolios']['Champion']['account']['cash'],'1009.12')

    def test_missing_stale_future_and_early_inputs_do_not_enter(self):
        data=fixture();data['predictions'].pop()
        self.assertEqual(run_cycle(self.bots,data,NOW)['common_signal_markets'],0)
        data=fixture();data['exported_at']=NOW-46
        self.assertEqual(run_cycle(self.bots,data,NOW)['input_status'],'STALE')
        data=fixture();data['predictions'][0]['recorded_at']=iso(NOW+1)
        run_cycle(self.bots,data,NOW)
        run_cycle(self.bots,fixture(),NOW,paused=True)
        for bot in self.bots.values(): self.assertFalse(bot.status()['positions'])

    def test_early_expired_neutral_and_unavailable_signals_skip(self):
        for kind in ('early','expired','neutral','not_available','old_signal'):
            data=fixture()
            if kind=='early':
                data['markets'][0].update(window_start=iso(NOW-700),window_end=iso(NOW+200))
            if kind=='expired':
                data['markets'][0].update(window_start=iso(NOW-900),window_end=iso(NOW))
            if kind=='neutral':
                for p in data['predictions']: p['predicted_up_probability']=.5
            if kind=='not_available': data['exported_at']=NOW+1
            if kind=='old_signal':
                for p in data['predictions']: p['recorded_at']=iso(NOW-91)
            run_cycle(self.bots,data,NOW)
            for bot in self.bots.values(): self.assertFalse(bot.status()['positions'],kind)

    def test_foreign_finality_does_not_pay_and_restart_preserves_entries(self):
        data=fixture();run_cycle(self.bots,data,NOW)
        data['markets'][0].update(settlement_status='VERIFIED',official_winner='UP',
            settled_at=iso(NOW+61),settlement_evidence='Official',contract_slug='wrong')
        run_cycle(self.bots,data,NOW+62)
        for bot in self.bots.values():
            self.assertEqual(bot.status()['positions'][0]['state'],'PAPER_OPEN')
        bot=self.bots['Champion'];bot.close()
        self.bots['Champion']=Sandbox(Path(self.tmp.name)/'Champion.sqlite',SandboxConfig(model_version=MODELS['Champion']))
        self.assertEqual(len(self.bots['Champion'].status()['positions']),1)
        with self.assertRaises(ValueError):
            Sandbox(Path(self.tmp.name)/'Champion.sqlite',replace(SandboxConfig(),model_version='different'))

    def test_export_reads_source_privately_and_only_fetches_public_predictions(self):
        source=Path(self.tmp.name)/'source.sqlite'
        output=Path(self.tmp.name)/'inputs.json'
        with sqlite3.connect(source) as db:
            db.execute('CREATE TABLE records (kind TEXT,payload TEXT)')
            db.execute('INSERT INTO records VALUES (?,?)',('market',json.dumps(fixture()['markets'][0])))
        before=source.read_bytes()
        requests=[]
        def get(request,timeout):
            self.assertEqual(request.get_method(),'GET')
            self.assertEqual(request.get_header('Apikey'),'sb_secret_fixture_not_real')
            self.assertIsNone(request.get_header('Authorization'))
            query=parse_qs(urlsplit(request.full_url).query)
            self.assertIn('recorded_at',query)
            requests.append(request)
            row=dict(market_slug=query['market_slug'][0][3:],model_version=query['model_version'][0][3:],
                     recorded_at=iso(NOW-5),predicted_up_probability=.8)
            return io.BytesIO(json.dumps([row]).encode())
        with patch.dict('os.environ',SUPABASE_URL='https://fixture.example',SUPABASE_KEY='sb_secret_fixture_not_real'),patch('trading_bot.dual_sandbox.urlopen',side_effect=get),patch('trading_bot.dual_sandbox.os.chown'),patch('trading_bot.dual_sandbox.time.time',return_value=NOW):
            export(source,output,123)
        self.assertEqual(len(requests),2)
        self.assertEqual(source.read_bytes(),before)
        self.assertEqual(output.stat().st_mode & 0o777,0o640)
        self.assertNotIn('sb_secret',output.read_text())


if __name__=='__main__': unittest.main()
