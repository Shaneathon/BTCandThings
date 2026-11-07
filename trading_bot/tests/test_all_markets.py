from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from trading_bot.dual_sandbox import (Sandbox,SandboxConfig,MarketSandboxConfig,
    MARKET_STREAMS,RESEARCH_MODEL,run_market_cycles,export)
from trading_bot.tests.test_dual_sandbox import NOW
from trading_bot.tests.test_bot import iso


class AllMarketTests(unittest.TestCase):
    def test_crypto_markets_independent_and_missing_metals_stay_paused(self):
        with tempfile.TemporaryDirectory() as temporary:
            bots={a+'_'+str(d//60)+'m':Sandbox(Path(temporary)/(a+str(d)+'.sqlite'),
                  MarketSandboxConfig(asset=a,duration_seconds=d,model_version=RESEARCH_MODEL)) for a,d in MARKET_STREAMS}
            markets=[];predictions=[]
            for asset,duration in MARKET_STREAMS:
                start=int(NOW)//duration*duration
                slug=asset+'-'+str(duration)
                markets.append(dict(market_slug=slug,asset=asset,duration_seconds=duration,
                    window_start=iso(start),window_end=iso(start+duration),contract_slug=slug+'-contract',
                    official_price_to_beat='100',settlement_status='PENDING'))
                if asset in ('GOLD','SILVER'): continue
                predictions.append(dict(market_slug=slug,model_version=RESEARCH_MODEL,recorded_at=iso(NOW-2),
                    source_timestamp=iso(NOW-5),predicted_up_probability=.8 if asset=='BTC' else .2))
            data=dict(exported_at=NOW-1,markets=markets,predictions=predictions)
            try:
                reports=run_market_cycles(bots,data,NOW)
                self.assertEqual(len(reports),8)
                for name,report in reports.items():
                    if name.startswith(('GOLD','SILVER')):
                        self.assertEqual(report['coverage_status'],'PAUSED_NO_FRESH_PREDICTION')
                        self.assertFalse(report['account']['positions'])
                    else:
                        self.assertEqual(len(report['account']['positions']),1)
                        position=report['account']['positions'][0]
                        self.assertTrue(name.startswith(position['asset']+'_'))
                        self.assertEqual(position['side'],'UP' if name.startswith('BTC_') else 'DOWN')
                    self.assertFalse(report['account']['live_orders_enabled'])
            finally:
                for bot in bots.values(): bot.close()

    def test_existing_bitcoin_settings_remain_unchanged(self):
        self.assertNotIn('asset',asdict(SandboxConfig()))
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'original.sqlite'
            first=Sandbox(path,SandboxConfig());first.close()
            again=Sandbox(path,SandboxConfig());again.close()
            with self.assertRaises(ValueError):
                Sandbox(path,MarketSandboxConfig(model_version=RESEARCH_MODEL))

    def test_remote_control_feed_outage_does_not_drop_local_research(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'source.sqlite';output=Path(temporary)/'export.json'
            prediction=dict(market_slug='eth-fixture',recorded_at=iso(NOW-2),source_timestamp=iso(NOW-5),
                            model_version=RESEARCH_MODEL,predicted_up_probability=.2)
            with sqlite3.connect(source) as db:
                db.execute('CREATE TABLE records (kind TEXT,payload TEXT)')
                db.execute('CREATE TABLE research_snapshots (recorded_at TEXT,payload TEXT)')
                db.execute('INSERT INTO research_snapshots VALUES (?,?)',(prediction['recorded_at'],json.dumps(prediction)))
            before=source.read_bytes()
            with patch.dict('os.environ',SUPABASE_URL='https://fixture.example',SUPABASE_KEY='sb_secret_fixture_not_real'),patch('trading_bot.dual_sandbox.urlopen',side_effect=URLError('fixture outage')),patch('trading_bot.dual_sandbox.os.chown'),patch('trading_bot.dual_sandbox.time.time',return_value=NOW):
                export(source,output,123,all_markets=True)
            result=json.loads(output.read_text())
            self.assertEqual(result['predictions'],[prediction])
            self.assertEqual(len(result['feed_errors']),2)
            self.assertEqual(before,source.read_bytes())
            self.assertNotIn('sb_secret',output.read_text())
