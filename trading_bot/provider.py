"""Strict binary contract adapter. No credentials and no order submission."""
from decimal import Decimal
import hashlib
import json
import re
from trading_bot.core import amount, time_of
from trading_bot.execution_audit import book_summary

FEE_BASIS='Published US taker schedule reported by support: 0.06; market metadata discrepancy retained.'


def corroboration(details):
    """Independent resolved-contract corroboration, never settlement guesses."""
    terms=details.get('assetPriceTerms') or {}
    if (details.get('status')!='MARKET_STATUS_RESOLVED' or details.get('closed') is not True
            or terms.get('marketType')!='ASSET_PRICE_MARKET_TYPE_UP_DOWN'):
        return None
    try:
        target,final=terms['priceToBeat'],terms['settlementPrice']
        if target['currency']!='USD' or final['currency']!='USD' or min(amount(target['value']),amount(final['value']))<=0: return None
        winner='UP' if amount(final['value'])>=amount(target['value']) else 'DOWN'
        sides=details['marketSides']
        yes=[s for s in sides if s.get('description')=='Yes' and s.get('long') is True]
        no=[s for s in sides if s.get('description')=='No' and s.get('long') is False]
        if len(sides)!=2 or len(yes)!=1 or len(no)!=1: return None
        prices=(amount(yes[0]['price']),amount(no[0]['price']))
        if prices not in ((Decimal(1),Decimal(0)),(Decimal(0),Decimal(1))): return None
        matches=(prices[0]==1)==(winner=='UP')
        key=str(terms['asset']['symbol']).upper()+'_'+terms['horizon']
        return key,winner,matches
    except (KeyError,TypeError,ValueError,ArithmeticError): return None


def mapping(m,details,proof):
    if details.get('slug')!=m['contract_slug']: raise ValueError('METADATA_IDENTITY')
    if details.get('closed') is True or details.get('status')=='MARKET_STATUS_RESOLVED': raise ValueError('CLOSED_METADATA')
    t=details.get('assetPriceTerms') or {}
    symbol={'GOLD':'gold','SILVER':'silver'}.get(m['asset'],m['asset'].lower())
    target=t.get('priceToBeat') or {}
    if (t.get('marketType')!='ASSET_PRICE_MARKET_TYPE_UP_DOWN' or (t.get('asset') or {}).get('symbol')!=symbol
            or time_of(t['windowStart'])!=time_of(m['window_start']) or time_of(t['windowEnd'])!=time_of(m['window_end'])
            or target.get('currency')!='USD' or amount(target['value'])!=amount(m['official_price_to_beat'])):
        raise ValueError('METADATA_TERMS')
    description=details.get('description','')
    if not re.search(r'This market will settle to Up if .*?greater than or equal to.*?Otherwise, this market will settle to Down\.',description,re.S|re.I):
        raise ValueError('UNREVIEWED_RULE_TEMPLATE')
    sides=details.get('marketSides')
    if not isinstance(sides,list) or len(sides)!=2: raise ValueError('UNREVIEWED_SIDES')
    yes=[s for s in sides if s.get('description')=='Yes' and s.get('long') is True]
    no=[s for s in sides if s.get('description')=='No' and s.get('long') is False]
    if (len(yes)!=1 or len(no)!=1 or any(s.get('identifier')!=m['contract_slug'] or s.get('tradable') is not True for s in sides)):
        raise ValueError('SIDE_IDENTITY')
    if proof.get('conflicts',0) or proof.get('UP',0)<1 or proof.get('DOWN',0)<1 or proof.get('total',0)<3:
        raise ValueError('MAPPING_NEEDS_RESOLVED_CORROBORATION')
    stable=dict(contract=m['contract_slug'],asset=m['asset'],start=m['window_start'],end=m['window_end'],
                target=str(amount(m['official_price_to_beat'])),rule='YES_LONG_IS_UP_TYPED_UP_DOWN_V1')
    evidence='RULE_TEMPLATE_AND_RESOLVED_CORROBORATION:'+hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest()
    return evidence


def directional_book(m,details,proof,response,request_started,received):
    evidence=mapping(m,details,proof)
    # Last transaction time is not the REST snapshot's reception time. Quiet
    # books can legitimately retain it; request/response freshness is checked.
    summary=book_summary(response,m['contract_slug'],received)
    if not 0<=received-request_started<=5: raise ValueError('SLOW_BOOK_REQUEST')
    if summary['exchange_age_seconds'] is not None and summary['exchange_age_seconds'] < -5:
        raise ValueError('FUTURE_EXCHANGE_BOOK')
    if not time_of(m['window_start'])<=received<time_of(m['window_end']): raise ValueError('CLOSED_WINDOW')
    raw=response['marketData']
    def levels(name,complement=False):
        result=[]
        for row in raw[name]:
            px=amount(row['px']['value'])
            if complement: px=1-px
            result.append(dict(price=str(px),quantity=str(amount(row['qty']))))
        return sorted(result,key=lambda r:amount(r['price']))
    common=dict(market_slug=m['market_slug'],contract_slug=m['contract_slug'],approved=True,
                mapping_evidence=evidence,request_started_at=request_started,received_at=received,
                exchange_last_transaction_at=summary['exchange_timestamp'])
    # A BUY_SHORT pays 1 minus the LONG bid; it consumes that bid's quantity.
    # This models binary complementary claims, not leveraged spot shorting.
    return {'UP':dict(**common,side='UP',intent='ORDER_INTENT_BUY_LONG',offers=levels('offers'),
                      liquidation_bids=sorted(levels('bids'),key=lambda r:amount(r['price']),reverse=True)),
            'DOWN':dict(**common,side='DOWN',intent='ORDER_INTENT_BUY_SHORT',offers=levels('bids',True),
                        liquidation_bids=sorted(levels('offers',True),key=lambda r:amount(r['price']),reverse=True))}


def evidence_packet(source):
    """Read-only, bounded latest evidence per contract; exported without secrets."""
    from pathlib import Path
    import sqlite3
    with sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute('''SELECT e.market_slug,e.payload FROM evidence e JOIN
          (SELECT market_slug,MAX(observed_at) observed_at FROM evidence GROUP BY market_slug) x
          ON e.market_slug=x.market_slug AND e.observed_at=x.observed_at
          ORDER BY e.observed_at DESC LIMIT 1000''').fetchall()
    metadata={};proofs={}
    for slug,payload in rows:
        details=json.loads(payload)
        metadata[slug]=details
        item=corroboration(details)
        if item:
            key,winner,matches=item
            row=proofs.setdefault(key,dict(total=0,UP=0,DOWN=0,conflicts=0))
            row['total']+=1;row[winner]+=1;row['conflicts']+=int(not matches)
    # Keep full metadata only for recent unclosed contracts; past contracts are
    # represented by aggregate corroboration, not duplicated in each export.
    metadata={k:v for k,v in metadata.items() if v.get('closed') is not True}
    return dict(metadata=metadata,proofs=proofs)
