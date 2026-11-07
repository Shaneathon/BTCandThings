import copy
import json
import tempfile
from pathlib import Path
import unittest
from collector import Store, iso
from ten_streams import collect
from test_ten_streams import fixture, NOW
from settlement import winner, reconcile
from cloud_sync import sync, Client
from simulation import simulate


class FakeCloud:
    def __init__(self):
        self.tables={}
        self.calls=[]
    def __call__(self,method,table,params=None,payload=None,prefer=None):
        self.calls.append((method,table,params,payload,prefer))
        rows=self.tables.setdefault(table,{})
        if method=='POST':
            fields=params['on_conflict'].split(',')
            for row in payload:
                key=tuple(row[k] for k in fields)
                if key not in rows or 'merge-duplicates' in prefer:
                    rows[key]=copy.deepcopy(row)
            return None
        if method=='GET' and 'market_slug' not in params:
            return list(rows.values())[:1]
        key=(params['market_slug'][3:],)
        if method=='GET':
            return [copy.deepcopy(rows[key])] if key in rows else []
        if method=='PATCH':
            if rows[key]['settlement_status']!='PENDING':
                return []
            rows[key].update(payload)
            return [copy.deepcopy(rows[key])]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:')
        collect(self.store,fixture,NOW)

    def tearDown(self):
        self.store.db.close()

    def test_candle_uploads_are_batched_and_failed_batches_retry_without_checkpoints(self):
        cloud=FakeCloud()
        def flaky(method,table,*args):
            if table=='asset_proxy_candles': raise TimeoutError()
            return cloud(method,table,*args)
        first=sync(self.store,flaky,limit=1000)
        self.assertGreater(first['errors'],100)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM cloud_checkpoints WHERE table_name='asset_proxy_candles'").fetchone()[0],0)
        second=sync(self.store,cloud,limit=1000)
        self.assertEqual(second['errors'],0)
        posts=[c for c in cloud.calls if c[0]=='POST' and c[1]=='asset_proxy_candles']
        self.assertTrue(all(len(c[3])<=100 for c in posts))
        count=self.store.db.execute("SELECT count(*) FROM records WHERE kind='candle'").fetchone()[0]
        self.assertEqual(len(cloud.tables['asset_proxy_candles']),count)
        self.assertLess(len(posts),count/10)

    def test_database_seed_is_consistent_private_and_never_overwrites(self):
        from storage import seed
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.sqlite'
            destination=Path(tmp)/'destination.sqlite'
            original=Store(source)
            collect(original,fixture,NOW)
            seed(source,destination)
            self.assertEqual(destination.stat().st_mode & 0o777,0o600)
            with __import__('sqlite3').connect(destination) as copy:
                self.assertEqual(copy.execute('SELECT count(*) FROM research_snapshots').fetchone()[0],8)
            before=destination.read_bytes()
            with self.assertRaises(FileExistsError): seed(source,destination)
            self.assertEqual(before,destination.read_bytes())
            original.db.close()

    def test_secure_configuration_is_exclusive_and_checks_tables_read_only(self):
        import os
        from configure_cloud import configure
        cloud=FakeCloud()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'research.env'
            configure(path,'https://example.supabase.co','fake-test-key',lambda *args:cloud)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertTrue(all(call[0]=='GET' for call in cloud.calls))
            with self.assertRaises(FileExistsError):
                configure(path,'https://example.supabase.co','fake-test-key',lambda *args:cloud)

    def test_raw_quotes_retained_without_inventing_semantic_mapping(self):
        from quotes import capture
        records=[json.loads(row[0]) for row in self.store.db.execute('SELECT payload FROM raw_quotes')]
        self.assertEqual(len(records),8)
        self.assertTrue(all(r['side_mapping_verified'] is False for r in records))
        market=json.loads(self.store.db.execute("SELECT payload FROM records WHERE kind='market' LIMIT 1").fetchone()[0])
        with self.assertRaises(ValueError):
            capture(self.store,lambda url:{'marketData':{'marketSlug':'wrong','bestBid':.4,'bestAsk':.5}},market,NOW)

    def test_missing_bbo_is_unavailable_not_type_error(self):
        from quotes import capture
        market=json.loads(self.store.db.execute("SELECT payload FROM records WHERE kind='market' LIMIT 1").fetchone()[0])
        for missing in (None, {}, {'value':None}, {'value':''}):
            response={'marketData':{'marketSlug':market['contract_slug'],'bestBid':missing,'bestAsk':.5}}
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'bestBid unavailable'):
                capture(self.store,lambda url:response,market,NOW)

    def test_live_resolved_status_still_requires_semantic_winner(self):
        self.assertIsNone(winner({'status':'MARKET_STATUS_RESOLVED','outcomePrices':['1','0']}))
        self.assertEqual(winner({'status':'MARKET_STATUS_RESOLVED','winningSide':'DOWN'}),'DOWN')
        self.assertIsNone(winner({'status':'MARKET_STATUS_RESOLVED','winningSide':1}))

    def test_official_typed_prices_live_schema_and_conflicts(self):
        def record(target, final):
            return {'status':'MARKET_STATUS_RESOLVED','closed':True,
                    'outcomes':'["Yes","No"]','outcomePrices':'["1","0"]',
                    'assetPriceTerms':{'marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                        'priceToBeat':{'value':target,'currency':'USD'},
                        'settlementPrice':{'value':final,'currency':'USD'}}}
        self.assertEqual(winner(record('75282.21','75612.66')),'UP')
        self.assertEqual(winner(record('2221.84','2220.38')),'DOWN')
        for value in ('2221.84','NaN','Infinity','-1','bad'):
            self.assertIsNone(winner(record('2221.84',value)))
        for field,value in [('closed',False),('status','OPEN'),('winningSide','DOWN')]:
            row=record('75282.21','75612.66');row[field]=value
            self.assertIsNone(winner(row))
        row=record('1','2');row['assetPriceTerms']['settlementPrice']['currency']='EUR'
        self.assertIsNone(winner(row))

    def test_tie_requires_explicit_contract_rule(self):
        row={'status':'MARKET_STATUS_RESOLVED','closed':True,
             'assetPriceTerms':{'marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                 'priceToBeat':{'value':'2221.84','currency':'USD'},
                 'settlementPrice':{'value':'2221.84','currency':'USD'}}}
        self.assertIsNone(winner(row))
        row['description']=('This market will settle to Up if the Ethereum price at 2:30AM ET '
            'on Nov 6, 2026 is greater than or equal to the price at 2:15AM ET on Nov 6, 2026. '
            'Otherwise, this market will settle to Down.')
        self.assertEqual(winner(row),'UP')
        row['winningSide']='DOWN'
        self.assertIsNone(winner(row))
        del row['winningSide']
        row['description']=row['description'].replace('greater than or equal to','greater than')
        self.assertIsNone(winner(row))

    def test_typed_prices_reconcile_but_foreign_terms_never_verify(self):
        def resolved(url,params=None):
            response=fixture(url,params)
            row=response.get('market')
            if row:
                row.update(status='MARKET_STATUS_RESOLVED',closed=True)
                row['assetPriceTerms']['settlementPrice']={'value':'999999','currency':'USD'}
            return response
        result=reconcile(self.store,resolved,NOW+301,limit=2)
        self.assertEqual(result['verified'],2)

    def test_finality_and_semantic_side_required(self):
        for record in [{'state':'OPEN','winningSide':'UP'}, {'state':'SETTLED','winningSide':1},
                       {'state':'SETTLED','winningSide':'1'},
                       {'state':'SETTLED','winningSide':'UP','winningOutcome':'DOWN'},
                       {'state':'SETTLED','status':'OPEN','winningSide':'UP'}]:
            self.assertIsNone(winner(record))
        self.assertEqual(winner({'state':'SETTLED','winningSide':'UP'}),'UP')

    def test_delayed_settlement_rotation_and_no_downgrade(self):
        def settled(url,params=None):
            response=fixture(url,params)
            if 'market' in response:
                response['market'].update(state='SETTLED',winningOutcome='UP')
            return response
        result=reconcile(self.store,settled,NOW+301,limit=2)
        self.assertEqual(result['verified'],2)
        result=reconcile(self.store,settled,NOW+301,limit=2)
        self.assertEqual(result['verified'],2)
        before=self.store.db.execute("SELECT count(*) FROM records WHERE kind='market' AND payload LIKE '%VERIFIED%'").fetchone()[0]
        collect(self.store,fixture,NOW+302)
        after=self.store.db.execute("SELECT count(*) FROM records WHERE kind='market' AND payload LIKE '%VERIFIED%'").fetchone()[0]
        self.assertGreaterEqual(after,before)

    def test_foreign_settlement_cannot_verify(self):
        def wrong(url,params=None):
            response=fixture(url,params)
            response['market']['assetPriceTerms']['asset']['symbol']='unknown'
            response['market'].update(state='SETTLED',winningOutcome='UP')
            return response
        result=reconcile(self.store,wrong,NOW+301)
        self.assertEqual(result['verified'],0)
        self.assertGreater(result['errors'],0)

    def test_sync_retry_and_natural_keys(self):
        send=FakeCloud()
        calls=send.calls
        failed=sync(self.store,lambda *args: (_ for _ in ()).throw(TimeoutError()),limit=2)
        self.assertEqual(failed['errors'],2)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM cloud_checkpoints').fetchone()[0],0)
        result=sync(self.store,send,limit=1000)
        self.assertEqual(result['errors'],0)
        self.assertGreater(result['sent'],10)
        again=sync(self.store,send,limit=1000)
        self.assertEqual(again['sent'],0)
        self.assertTrue(all(table.startswith('asset_') for _,table,_,_,_ in calls))
        self.assertTrue(all('on_conflict' in params for method,_,params,_,_ in calls if method=='POST'))

    def test_end_to_end_collection_settlement_cloud_and_paper_accounting(self):
        cloud=FakeCloud()
        self.assertEqual(sync(self.store,cloud,limit=1000)['errors'],0)
        def settled(url,params=None):
            response=fixture(url,params)
            if 'market' in response:
                response['market'].update(state='SETTLED',winningSide='UP')
            return response
        self.assertGreater(reconcile(self.store,settled,NOW+901,limit=100)['verified'],0)
        result=sync(self.store,cloud,limit=1000)
        self.assertEqual(result['errors'],0)
        markets=list(cloud.tables['asset_market_windows'].values())
        predictions=list(cloud.tables['asset_market_predictions'].values())
        self.assertEqual(len(predictions),8)
        quotes=[dict(market_slug=m['market_slug'],contract_slug=m['contract_slug'],captured_at=iso(NOW+1),
                     up_ask=.6,down_ask=.45,side_mapping_verified=True,source_name='Polymarket US') for m in markets]
        result=simulate(markets,predictions,quotes,10,.01,.02)
        self.assertEqual(result['closed'],8)
        self.assertAlmostEqual(result['realized_pnl'],29.6)
        # A conflicting official cloud outcome may never be overwritten.
        key=next(k for k,v in cloud.tables['asset_market_windows'].items() if v['settlement_status']=='VERIFIED')
        cloud.tables['asset_market_windows'][key]['official_winner']='DOWN'
        self.store.db.execute('DELETE FROM cloud_checkpoints')
        self.store.db.commit()
        self.assertGreater(sync(self.store,cloud,limit=1000)['errors'],0)
        self.assertEqual(cloud.tables['asset_market_windows'][key]['official_winner'],'DOWN')

    def test_client_rejects_unsafe_origins_and_destinations(self):
        for url in ['http://example.com','https://user:secret@example.com','https://example.com/path','https://example.com?key=x']:
            with self.assertRaises(ValueError):
                Client(url,'not-a-real-key')
        client=Client('https://example.supabase.co','not-a-real-key')
        with self.assertRaises(ValueError):
            client('POST','btc_markets',payload={})

    def test_settlement_simulation_fees_timing_and_missing_quote(self):
        market=dict(market_slug='m',window_start=iso(NOW-60),window_end=iso(NOW+300),
                    contract_slug='c',settlement_status='VERIFIED',official_winner='UP',settlement_evidence='official evidence')
        prediction=dict(market_slug='m',model_version='v1',recorded_at=iso(NOW),source_timestamp=iso(NOW-1),
                        predicted_up_probability=.7,lean_direction='UP')
        quote=dict(market_slug='m',contract_slug='c',captured_at=iso(NOW+1),up_ask=.6,down_ask=.45,
                   side_mapping_verified=True,source_name='Polymarket US')
        result=simulate([market],[prediction],[quote],10,.01,.02)
        self.assertEqual(result['closed'],1)
        self.assertAlmostEqual(result['realized_pnl'],3.7)
        for field,value in [('captured_at',iso(NOW-1)),('captured_at',iso(NOW+31)),('contract_slug','wrong'),('side_mapping_verified',False)]:
            bad={**quote,field:value}
            self.assertEqual(simulate([market],[prediction],[bad],10,.01,.02)['closed'],0)
        self.assertEqual(simulate([market],[{**prediction,'source_timestamp':iso(NOW+1)}],[quote],10,.01,.02)['closed'],0)
        self.assertEqual(simulate([{**market,'settlement_status':'PENDING'}],[prediction],[quote],10,.01,.02)['closed'],0)
        with self.assertRaises(ValueError):
            simulate([market],[prediction],[quote],10,-.01,.02)


if __name__=='__main__':
    unittest.main()
