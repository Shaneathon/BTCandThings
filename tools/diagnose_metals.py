#!/usr/bin/env python3
"""Read-only metals feed and exact current-contract diagnosis; no orders/restarts."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen


def service(name,field):
    return subprocess.run(['systemctl','show',name,'-p',field,'--value'],capture_output=True,text=True,check=False).stdout.strip()


def main():
    now=time.time()
    root=Path(service('btc-multiasset-research','WorkingDirectory'))
    print('READ-ONLY METALS DIAGNOSIS',time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime(now)))
    print('Services:',json.dumps({name:service(name,'ActiveState') for name in ('btc-metals-proxy','btc-multiasset-research')}))
    print('Research source:',str(root))
    unit=Path('/etc/systemd/system/btc-multiasset-research.service')
    print('Research unit explicitly selects local metals proxy:',unit.exists() and 'BTC_METALS_PROXY_URL=http://127.0.0.1:8770' in unit.read_text())
    # Only print public metals status. Never display service environments/credentials.
    dbpath=Path('/var/lib/btcandthings-research/research.sqlite')
    if dbpath.exists():
        with sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True) as db:
            row=db.execute('SELECT observed_at,payload FROM collector_status WHERE singleton=1').fetchone()
            if row:
                data=json.loads(row[1]);print('Collector status age seconds:',round(now-row[0],1))
                for asset in ('GOLD','SILVER'):
                    print(asset,'collector:',json.dumps(dict(feed=data.get('assets',{}).get(asset),stream=data.get('streams',{}).get(asset+'_15m'))))
    for asset in ('GOLD','SILVER'):
        try:
            with urlopen('http://127.0.0.1:8770/candles?asset='+asset,timeout=5) as response:
                data=json.load(response)
            bars=data.get('candles',[])
            print(asset,'proxy:',json.dumps(dict(completed_candles=len(bars),required=data.get('minimum_research_candles'),
                newest_completed_bar_age_seconds=round(now-bars[-1]['time']-60,1) if bars else None,
                feed_status=data.get('feed_status'),is_official_settlement_feed=data.get('is_official_settlement_feed'))))
        except Exception as error:
            print(asset,'proxy unavailable:',type(error).__name__)
    cache=Path('/var/lib/btc-metals-proxy/quotes.sqlite')
    if cache.exists():
        with sqlite3.connect(cache.resolve().as_uri()+'?mode=ro',uri=True) as db:
            for asset in ('GOLD','SILVER'):
                stamps=[r[0] for r in db.execute('SELECT source_at FROM quotes WHERE asset=? AND source_at>=? ORDER BY source_at',(asset,now-7200))]
                grouped={}
                for stamp in stamps: grouped.setdefault(int(stamp)//60,[]).append(stamp)
                complete=[points for minute,points in grouped.items() if minute*60+60<=now]
                print(asset,'two-hour sampling:',json.dumps(dict(distinct_updates=len(stamps),observed_complete_minutes=len(complete),
                    minutes_meeting_bar_rule=sum(len(p)>=2 and p[-1]-p[0]>=30 for p in complete),
                    largest_update_gap_seconds=round(max((b-a for a,b in zip(stamps,stamps[1:])),default=0),1))))
    sys.path.insert(0,str(root/'collection'))
    try:
        from ten_streams import market,get_json
    except Exception as error:
        print('Runtime market check could not import installed collector:',type(error).__name__);return
    for asset in ('GOLD','SILVER'):
        observed=time.time();start=int(observed)//900*900
        try:
            row,details=market(get_json,asset,'15m',start,observed)
            print(asset,'CURRENT CONTRACT VERIFIED:',json.dumps({k:row.get(k) for k in ('market_slug','contract_slug','official_price_to_beat','window_end')}))
        except Exception as error:
            print(asset,'current contract:',json.dumps(dict(error=type(error).__name__,http_status=getattr(error,'code',None),
                validation_reason=str(error)[:200] if isinstance(error,ValueError) else None)))
            if getattr(error,'code',None)==429:
                print('Stopping public checks after rate limit.');break
    print('No services, history, strategies or trading settings changed.')


if __name__=='__main__': main()
