"""Opt-in Supabase synchronization. Only three dedicated asset_* tables allowed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

TABLES = {'market':('asset_market_windows','market_slug'),
          'candle':('asset_proxy_candles','asset,source_name,interval_seconds,candle_open'),
          'prediction':('asset_market_predictions','market_slug,recorded_at,model_version')}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, url, key):
        parsed=urlsplit(url)
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('','/') or parsed.query or parsed.fragment):
            raise ValueError('Expected a plain HTTPS Supabase origin')
        if not key:
            raise ValueError('Missing server-only Supabase credential')
        self.url=url.rstrip('/')
        self.key=key
        self.opener=build_opener(NoRedirect())

    def __call__(self, method, table, params=None, payload=None, prefer=None):
        if table not in {v[0] for v in TABLES.values()} or method not in ('GET','POST','PATCH'):
            raise ValueError('Destination not permitted')
        headers={'apikey':self.key,'Content-Type':'application/json'}
        if not self.key.startswith('sb_secret_'):
            headers['Authorization']='Bearer '+self.key
        if prefer:
            headers['Prefer']=prefer
        body=None if payload is None else json.dumps(payload,allow_nan=False).encode()
        request=Request(self.url+'/rest/v1/'+table+'?'+urlencode(params or {}),data=body,headers=headers,method=method)
        # No automatic POST/PATCH retries here: durable checkpoints plus natural
        # keys make the next pass retry safe without printing server error bodies.
        with self.opener.open(request,timeout=20) as response:
            raw=response.read(4_000_001)
            if len(raw)>4_000_000:
                raise ValueError('Oversized response')
            return json.loads(raw) if raw else None


def checkpoint_key(row, fields):
    return json.dumps([row[field] for field in fields.split(',')],separators=(',',':'))


def sync(store, send, limit=500):
    store.db.execute('''CREATE TABLE IF NOT EXISTS cloud_checkpoints (
        table_name TEXT, row_key TEXT, digest TEXT, PRIMARY KEY(table_name,row_key))''')
    store.db.commit()
    report=dict(sent=0, unchanged=0, errors=0, batch_limit=limit)
    blocked_markets=set()
    rows=[(kind,json.loads(payload)) for kind,payload in store.db.execute('SELECT kind,payload FROM records ORDER BY CASE kind WHEN \'market\' THEN 0 ELSE 1 END,key')]
    rows += [('prediction',json.loads(payload)) for (payload,) in store.db.execute('SELECT payload FROM research_snapshots ORDER BY recorded_at,market_slug')]
    pending=[]
    def flush():
        if not pending: return
        kind,table,fields=pending[0][:3]
        mode='ignore' if kind=='prediction' else 'merge'
        try:
            send('POST',table,{'on_conflict':fields},[item[5] for item in pending],f'resolution={mode}-duplicates,return=minimal')
            with store.db:
                store.db.executemany('INSERT INTO cloud_checkpoints VALUES (?,?,?) ON CONFLICT(table_name,row_key) DO UPDATE SET digest=excluded.digest',
                                     [(item[1],item[3],item[4]) for item in pending])
            report['sent']+=len(pending)
        except Exception as exc:
            report['errors']+=len(pending)
            name=type(exc).__name__+('_'+str(exc.code) if getattr(exc,'code',None) else '')
            report.setdefault('error_types',{})[name]=report.setdefault('error_types',{}).get(name,0)+len(pending)
        pending.clear()
    for kind,row in rows:
        if pending and pending[0][0]!=kind: flush()
        if report['sent']+report['errors']+len(pending)>=limit:
            flush()
            break
        if kind not in TABLES:
            report['errors']+=1
            continue
        if kind=='prediction' and row['market_slug'] in blocked_markets:
            report['errors']+=1
            continue
        table,fields=TABLES[kind]
        digest=hashlib.sha256(json.dumps(row,sort_keys=True,allow_nan=False).encode()).hexdigest()
        key=checkpoint_key(row,fields)
        old=store.db.execute('SELECT digest FROM cloud_checkpoints WHERE table_name=? AND row_key=?',(table,key)).fetchone()
        if old and old[0]==digest:
            report['unchanged']+=1
            continue
        try:
            if kind=='market':
                if row['settlement_status']=='VERIFIED' and (row.get('official_winner') not in ('UP','DOWN') or not row.get('settlement_evidence')):
                    raise ValueError('Unverified settlement claim')
                # Insert initial identity without overwriting an existing final.
                send('POST',table,{'on_conflict':fields},[row],'resolution=ignore-duplicates,return=minimal')
                remote=send('GET',table,{'market_slug':'eq.'+row['market_slug'],'select':'*'})
                if not isinstance(remote,list) or len(remote)!=1:
                    raise ValueError('Missing remote market')
                other=remote[0]
                for field in ('asset','duration_seconds','contract_slug'):
                    if other.get(field)!=row[field]:
                        raise ValueError('Remote market identity conflict')
                from collector import epoch
                for field in ('window_start','window_end'):
                    if epoch(other[field])!=epoch(row[field]):
                        raise ValueError('Remote market window conflict')
                if float(other['official_price_to_beat'])!=float(row['official_price_to_beat']):
                    raise ValueError('Remote target conflict')
                if row['settlement_status']=='VERIFIED':
                    if other.get('settlement_status')=='VERIFIED':
                        if other.get('official_winner')!=row['official_winner']:
                            raise ValueError('Conflicting verified outcome')
                    elif other.get('settlement_status')=='PENDING':
                        update={k:row[k] for k in ('settlement_status','official_winner','settlement_evidence','settled_at','updated_at')}
                        updated=send('PATCH',table,{'market_slug':'eq.'+row['market_slug'],'settlement_status':'eq.PENDING'},update,'return=representation')
                        if not isinstance(updated,list) or len(updated)!=1 or updated[0].get('official_winner')!=row['official_winner']:
                            raise ValueError('Settlement update unconfirmed; retry required')
                    else:
                        raise ValueError('Remote market requires manual reconciliation')
            else:
                pending.append((kind,table,fields,key,digest,row))
                if len(pending)>=100 or report['sent']+report['errors']+len(pending)>=limit: flush()
                continue
            with store.db:
                store.db.execute('INSERT INTO cloud_checkpoints VALUES (?,?,?) ON CONFLICT(table_name,row_key) DO UPDATE SET digest=excluded.digest',(table,key,digest))
            report['sent']+=1
        except Exception:
            if kind=='market':
                blocked_markets.add(row['market_slug'])
            report['errors']+=1
    flush()
    report['more_possible'] = report['sent']+report['errors'] >= limit
    return report


def main():
    from collector import Store
    from ten_streams import initialize
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--apply',action='store_true',help='Explicitly enable network writes to dedicated asset tables')
    args=parser.parse_args()
    if not args.apply:
        parser.error('Network writes require --apply. No upload performed.')
    if not args.db.is_file():
        parser.error('Existing local collector database required')
    client=Client(os.environ.get('BTC_RESEARCH_SUPABASE_URL',''),os.environ.get('BTC_RESEARCH_SUPABASE_KEY',''))
    store=Store(args.db)
    try:
        initialize(store)
        result=sync(store,client)
        print(json.dumps(result))
        raise SystemExit(1 if result['errors'] else 0)
    finally:
        store.db.close()


if __name__=='__main__':
    main()
