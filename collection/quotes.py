"""Archive exact-contract BBO evidence, without assuming LONG/SHORT side mapping.

Route/response shape verified against polymarket-us 2.4.1 SDK source, not a live
response. Raw bids/asks are not automatically promoted to simulation fills.
"""
import json
import math
from urllib.parse import quote
from collector import iso


def capture(store,get,market,observed):
    contract=market['contract_slug']
    response=get('https://gateway.polymarket.us/v1/markets/'+quote(contract,safe='')+'/bbo')
    md=response.get('marketData') if isinstance(response,dict) else None
    if not isinstance(md,dict) or md.get('marketSlug')!=contract:
        raise ValueError('BBO contract identity unverified')
    values=[]
    for key in ('bestBid','bestAsk'):
        value=md.get(key)
        number=float(value.get('value') if isinstance(value,dict) else value)
        if not math.isfinite(number) or not 0<=number<=1:
            raise ValueError('Invalid BBO price')
        values.append(number)
    if values[0]>values[1]:
        raise ValueError('Crossed BBO')
    row=dict(market_slug=market['market_slug'],contract_slug=contract,captured_at=iso(observed),
             source_name='Polymarket US',side_mapping_verified=False,raw=response)
    with store.db:
        store.db.execute('INSERT OR IGNORE INTO raw_quotes VALUES (?,?,?)',
                         (row['market_slug'],row['captured_at'],json.dumps(row,allow_nan=False)))
    return row
