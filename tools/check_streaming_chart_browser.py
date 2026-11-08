"""Browser contract test with real chart library and simulated Kraken v2 feed.

Pass --library /path/to/pinned/lightweight-charts-4.2.2.js. This test does not
claim that a live Kraken connection was verified.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time
import pandas as pd
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'BTCandThings_Website'/'BTCandThings_Upload'))
from market_candles import streaming_candles_html


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--library',type=Path,required=True)
    args=parser.parse_args()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        for asset in ('BTC','ETH','XRP','SOL'):
            for interval in ('1m','5m'):
                minutes=int(interval[:-1]);start=int(time.time())//(minutes*60)*(minutes*60)
                frame=pd.DataFrame([dict(time=pd.Timestamp.fromtimestamp(start-minutes*60,tz='UTC'),open=100,high=101,low=99,close=100)])
                html=streaming_candles_html(frame,asset,interval,100.5)
                page=browser.new_page(viewport=dict(width=700,height=300));errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('https://cdn.jsdelivr.net/**',lambda route:route.fulfill(path=str(args.library),content_type='application/javascript'))
                page.add_init_script('')
                mock='''window.__sockets=[];window.WebSocket=class {
                  static OPEN=1;static CLOSED=3;
                  constructor(url){this.url=url;this.readyState=1;window.__sockets.push(this);setTimeout(()=>this.onopen&&this.onopen(),0);}
                  send(value){window.__subscription=JSON.parse(value);}
                  close(){this.readyState=3;if(this.onclose)this.onclose();}
                };'''
                page.set_content(html.replace('<script>\n    const cfg=', '<script>'+mock+'\n    const cfg='),wait_until='load')
                page.wait_for_function('window.__subscription !== undefined')
                subscription=page.evaluate('window.__subscription')
                assert subscription['params']['symbol']==[asset+'/USD']
                assert subscription['params']['interval']==minutes
                stamp=datetime.fromtimestamp(start,timezone.utc).isoformat().replace('+00:00','Z')
                message=dict(channel='ohlc',type='update',data=[dict(symbol=asset+'/USD',interval=minutes,interval_begin=stamp,open=100,high=103,low=99,close=102)])
                page.evaluate('(msg)=>window.__sockets.at(-1).onmessage({data:JSON.stringify(msg)})',message)
                assert page.locator('#price').inner_text()=='$102'
                assert 'STREAMING' in page.locator('#feed').inner_text()
                message['data'][0]['close']=101
                page.evaluate('(msg)=>window.__sockets.at(-1).onmessage({data:JSON.stringify(msg)})',message)
                assert page.locator('#price').inner_text()=='$101'
                message['data'][0]['high']=98
                page.evaluate('(msg)=>window.__sockets.at(-1).onmessage({data:JSON.stringify(msg)})',message)
                assert page.locator('#price').inner_text()=='$101' # invalid OHLC ignored
                page.evaluate('window.__sockets.at(-1).close()')
                assert 'Disconnected' in page.locator('#feed').inner_text()
                page.wait_for_function('window.__sockets.length===2')
                assert not errors,errors
                assert page.locator('canvas').count()>0
                if asset=='BTC' and interval=='1m': page.screenshot(path='/tmp/kraken-streaming-chart.png')
                page.close();print('PASS',asset,interval,'incremental updates, invalid-data rejection and reconnection')
        browser.close()

if __name__=='__main__': main()
