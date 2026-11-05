"""Coinbase Advanced public SPOT data; no authentication or order endpoints.

Routes and fields checked against official coinbase-advanced-py 1.8.4 source.
Live endpoint compatibility is not yet verified in this restricted environment.
"""
from datetime import datetime
from decimal import Decimal
import json
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen

PRODUCTS=('BTC-USD','ETH-USD','XRP-USD','SOL-USD')
BASE='https://api.coinbase.com/api/v3/brokerage/market'


def positive(value,zero=False):
    if isinstance(value,bool): raise ValueError('Invalid numeric field')
    result=Decimal(str(value))
    if not result.is_finite() or result<0 or (not zero and result==0): raise ValueError('Invalid numeric field')
    return result


def timestamp(value):
    if isinstance(value,dict):
        seconds=int(value['seconds']); nanos=int(value.get('nanos',0))
        if not 0<=nanos<1_000_000_000: raise ValueError('Invalid book time')
        return seconds+nanos/1_000_000_000
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None: raise ValueError('Timezone required')
    return parsed.timestamp()


def get_json(url,params=None):
    if not url.startswith(BASE+'/'): raise ValueError('Only public Coinbase market routes allowed')
    request=Request(url+('?' + urlencode(params) if params else ''),headers={'User-Agent':'CBot-Paper-Research/0.1'})
    with urlopen(request,timeout=10) as response:
        data=response.read(4_000_001)
        if len(data)>4_000_000: raise ValueError('Oversized response')
        return json.loads(data)


def fetch_product(product,now=None,get=get_json):
    fixed_time=now is not None
    now=time.time() if now is None else now
    if product not in PRODUCTS: raise ValueError('Unsupported paper product')
    metadata=get(BASE+'/products/'+product)
    base,quote=product.split('-')
    if (metadata.get('product_id')!=product or metadata.get('product_type')!='SPOT'
            or metadata.get('base_currency_id')!=base or metadata.get('quote_currency_id')!=quote
            or str(metadata.get('status','')).upper()!='ONLINE' or metadata.get('trading_disabled') is not False):
        raise ValueError('Product identity or trading status unverified')
    if any(metadata.get(k) for k in ('cancel_only','post_only','auction_mode','is_disabled','view_only')):
        raise ValueError('Product restricted')
    for field in ('base_increment','quote_increment','base_min_size','quote_min_size'):
        positive(metadata[field])
    end=int(now)//60*60
    payload=get(BASE+'/products/'+product+'/candles',{'start':str(end-120*60),'end':str(end),
                                                      'granularity':'ONE_MINUTE','limit':'120'})
    bars={}
    for row in payload.get('candles',[]):
        start=int(row['start'])
        if start%60: raise ValueError('Unaligned candle')
        if start+60>now: continue
        values=[positive(row[k]) for k in ('open','high','low','close')]
        o,h,l,c=values
        positive(row['volume'],zero=True)
        if h<max(o,l,c) or l>min(o,h,c): raise ValueError('Invalid OHLC')
        normalized={**row,'start':start}
        if start in bars and bars[start]!=normalized: raise ValueError('Conflicting candle duplicate')
        bars[start]=normalized
    ordered=[bars[t] for t in sorted(bars)]
    if len(ordered)<60: raise ValueError('At least 60 completed candles required')
    if not 0<=now-(ordered[-1]['start']+60)<=120: raise ValueError('Stale candles')
    if any(b['start']-a['start']!=60 for a,b in zip(ordered,ordered[1:])): raise ValueError('Candle gaps')
    book=get(BASE+'/product_book',{'product_id':product,'limit':'1'}).get('pricebook',{})
    if book.get('product_id')!=product: raise ValueError('Wrong book product')
    if not fixed_time: now=time.time()
    source_time=timestamp(book['time'])
    if not 0<=now-source_time<=15: raise ValueError('Stale or future book')
    bid,ask=book['bids'][0],book['asks'][0]
    bid_px,ask_px=positive(bid['price']),positive(ask['price'])
    positive(bid['size']); positive(ask['size'])
    if bid_px>ask_px: raise ValueError('Crossed book')
    return dict(product_id=product,observed_at=now,book_time=source_time,metadata=metadata,
                candles=ordered,bid=str(bid_px),ask=str(ask_px),bid_size=bid['size'],ask_size=ask['size'])


def fetch_all(now=None,get=get_json):
    result={}
    for product in PRODUCTS:
        try: result[product]=fetch_product(product,now,get)
        except Exception as exc: result[product]={'product_id':product,'error':type(exc).__name__}
    return result


def momentum(snapshot):
    close=[positive(bar['close']) for bar in snapshot['candles']]
    def ema(span):
        value=close[0]; alpha=Decimal(2)/Decimal(span+1)
        for price in close[1:]: value=alpha*price+(1-alpha)*value
        return value
    fast,slow=ema(9),ema(21)
    change=close[-1]/close[-4]-1
    direction='BUY' if fast>slow and change>0 else 'SELL' if fast<slow and change<0 else 'HOLD'
    return dict(direction=direction,ema9=str(fast),ema21=str(slow),return3=str(change),
                candle_end=snapshot['candles'][-1]['start']+60)
