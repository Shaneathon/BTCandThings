"""Publish only whitelisted, timestamped BTC model observations; never publish secrets."""
import json, os, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

base=os.environ['SUPABASE_URL'].strip().rstrip('/')
key=os.environ['SUPABASE_KEY'].strip()
if not base.startswith('https://') or not key:
    raise RuntimeError('Invalid Supabase configuration')

def fetch(table, params):
    url=base+'/rest/v1/'+table+'?'+urllib.parse.urlencode(params)
    headers={'apikey':key,'Accept':'application/json'}
    if not key.startswith('sb_secret_'):
        headers['Authorization']='Bearer '+key
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=25) as response:
                return json.load(response)
now=datetime.now(timezone.utc)
since=(now-timedelta(hours=6)).isoformat()
rows=[]
for offset in range(0,5000,1000):
    batch=fetch('btc_predictions',{
        'select':'market_slug,recorded_at,seconds_remaining,predicted_up_probability,predicted_down_probability,model_version',
        'recorded_at':'gte.'+since,'order':'recorded_at.asc','limit':1000,'offset':offset})
    rows.extend(batch)
    if len(batch)<1000: break
else:
    raise RuntimeError('Export exceeded 5000 records; refusing incomplete publication')

market_slugs=sorted({r.get('market_slug') for r in rows if r.get('market_slug')})
markets=[]
for offset in range(0,3000,1000):
    batch=fetch('btc_markets',{
        'select':'market_slug,window_start,window_end,settlement_status,official_winner',
        'window_end':'gte.'+(now-timedelta(hours=26)).isoformat(),
        'order':'window_end.asc','limit':1000,'offset':offset})
    markets.extend(batch)
    if len(batch)<1000: break
else:
    raise RuntimeError('Market export exceeded 3000 records')

allowed={'market_slug','recorded_at','seconds_remaining','predicted_up_probability','predicted_down_probability','model_version'}
clean=[]
for row in rows:
    r={k:row.get(k) for k in allowed}
    p=r.get('predicted_up_probability')
    if p is not None and not (0<=float(p)<=1): continue
    clean.append(r)
result={
 'schema_version':1,'generated_at':now.isoformat(),
 'disclaimer':'Research predictions only. Missing observations are not backfilled. Settlement winner only when independently verified.',
 'predictions':clean,
 'markets':[{k:m.get(k) for k in ('market_slug','window_start','window_end','settlement_status','official_winner')} for m in markets if m.get('market_slug') in market_slugs]
}
path=Path('public/btc_predictions.json');path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print('Exported',len(clean),'predictions and',len(result['markets']),'markets')
