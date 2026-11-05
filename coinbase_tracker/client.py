"""Server-side reader for coin.shaneathon.com research data. No credentials in UI."""
import json
import time
from urllib.parse import urlsplit
from urllib.request import Request,build_opener
from trading_bot.status_client import NoRedirect
from coinbase_bot.market_data import PRODUCTS


def fetch(url,token):
    parsed=urlsplit(url)
    local=parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')
    if ((parsed.scheme!='https' and not local) or not parsed.hostname or parsed.username or parsed.password
            or parsed.path!='/status' or parsed.query or parsed.fragment or len(token)<32):
        raise ValueError('Configure an authenticated HTTPS tracker /status endpoint')
    request=Request(url,headers={'Authorization':'Bearer '+token},method='GET')
    with build_opener(NoRedirect()).open(request,timeout=5) as response:
        raw=response.read(4_000_001)
        if len(raw)>4_000_000: raise ValueError('Oversized tracker response')
        result=json.loads(raw)
    if result.get('mode')!='RESEARCH_TRACKER' or result.get('venue')!='Coinbase Advanced' or result.get('orders_enabled') is not False:
        raise ValueError('Wrong source or unexpected trading mode')
    return result


def bot_inputs(report,now=None):
    now=time.time() if now is None else now
    if (report.get('mode')!='RESEARCH_TRACKER' or report.get('venue')!='Coinbase Advanced' or report.get('orders_enabled') is not False
            or not 0<=now-report['observed_at']<=120):
        raise ValueError('Stale or foreign tracker')
    result={}
    for product in PRODUCTS:
        source=report.get('products',{}).get(product,{})
        result[product]=(source['bot_input'] if source.get('bot_ready') and 'bot_input' in source
                         else {'product_id':product,'error':'TRACKER_COMPONENT_NOT_READY'})
    return result
