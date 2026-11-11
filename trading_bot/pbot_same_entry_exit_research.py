#!/usr/bin/env python3
"""Research-only same-entry BTC15 exit comparison. Never modifies any database.
Quotes must support full quantity; gaps >5 seconds make timer-based exits uncertain.
Missing quote coverage is reported as unresolved, never imputed as settlement.
"""
import sqlite3,json,collections,math,datetime,argparse
from decimal import Decimal
def num(x):
 try:
  y=float(x);return y if math.isfinite(y) else None
 except (ValueError,TypeError):return None
def ts(x):
 if isinstance(x,(float,int)):return num(x)
 try:
  s=str(x)
  if s.replace('.','',1).isdigit():return num(s)
  return datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
 except (ValueError,TypeError,OverflowError):return None
def ro(path):
 db=sqlite3.connect('file:'+path+'?mode=ro',uri=True);db.execute('PRAGMA query_only=ON');return db
def outcome_map(db):
 out={};conflicts=set()
 for slug,raw in db.execute('SELECT market_slug,payload FROM evidence ORDER BY observed_at'):
  try:
   d=json.loads(raw);a=d.get('assetPriceTerms') or {}
   if d.get('status')!='MARKET_STATUS_RESOLVED' or d.get('closed') is not True:continue
   if a.get('marketType')!='ASSET_PRICE_MARKET_TYPE_UP_DOWN' or (a.get('asset') or {}).get('symbol','').lower() not in ('btc','xbt'):continue
   start,end=ts(a.get('windowStart')),ts(a.get('windowEnd'))
   beat=a.get('priceToBeat') or {};settle=a.get('settlementPrice') or {}
   target,final=num(beat.get('value')),num(settle.get('value'))
   if None in (start,end,target,final) or abs(end-start-900)>1 or min(target,final)<=0 or beat.get('currency')!='USD' or settle.get('currency')!='USD':continue
   winner='UP' if final>=target else 'DOWN'
   sides=d.get('marketSides') or []
   yes=[x for x in sides if x.get('description')=='Yes' and x.get('long') is True]
   no=[x for x in sides if x.get('description')=='No' and x.get('long') is False]
   if len(yes)!=1 or len(no)!=1 or (num(yes[0].get('price')),num(no[0].get('price')))!=((1.,0.) if winner=='UP' else (0.,1.)):continue
   ident=(start,end,round(target,5),winner)
   if slug in out and out[slug]!=ident:conflicts.add(slug)
   out[slug]=ident
  except (ValueError,TypeError,KeyError):continue
 for slug in conflicts:out.pop(slug,None)
 return out,len(conflicts)
def proceeds(levels,qty):
 remaining=qty;gross=0.;fee=0.
 for x in levels:
  price,depth=num(x.get('price')),num(x.get('quantity'))
  if price is None or depth is None or not 0<price<1 or depth<=0:continue
  take=min(remaining,depth);gross+=take*price;fee+=take*.06*price*(1-price);remaining-=take
  if remaining<=1e-7:return gross-fee
 return None
def evaluate(p,rows,winner,rule):
 qty,cost,entry,opened=(num(p.get(k)) for k in ('quantity','cost','entry_market_probability','opened_at'))
 if None in (qty,cost,opened) or qty<=0:return ('missing_entry_data',None)
 if rule=='hold':return ('settlement',(qty if winner==p['side'] else 0)-cost)
 if entry is None:return ('missing_entry_probability',None)
 side=p['side'];after=[r for r in rows if r[0]>=opened]
 if not after:return ('no_post_entry_quotes',None)
 stop,hold={'stop2':(.02,0),'stop3_15':(.03,15),'stop5_30':(.05,30),'trail':(.05,30)}[rule]
 stop_since=None;peak=None;previous=None;uncertain=False
 for stamp,prob,bids in after:
  if previous is not None and stamp-previous>5:
   stop_since=None;uncertain=True
  previous=stamp
  if not 0<=prob<=1:continue
  if prob<=entry-stop:
   if stop_since is None:stop_since=stamp
   if stamp-stop_since>=hold:
    money=proceeds(bids,qty)
    return ('stop',money-cost) if money is not None else ('insufficient_bid_depth',None)
  else:stop_since=None
  if rule=='trail':
   if prob>=.70:peak=max(prob,peak or prob)
   if peak is not None:
    money=proceeds(bids,qty)
    if money is not None and money>cost and (prob>=.75 or (prob>=.70 and prob<=peak-.01)):
     return ('profit_exit',money-cost)
 if uncertain:return ('unresolved_quote_gaps',None)
 return ('unresolved_no_exit_observed',None)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--ledger',default='/var/lib/pbot/observed-v1.sqlite');ap.add_argument('--research',default='/var/lib/private/btcandthings-research/research.sqlite');a=ap.parse_args()
 db=ro(a.ledger);research=ro(a.research);out,conflicts=outcome_map(research)
 positions=[];excluded=collections.Counter()
 for wallet,slug,raw in db.execute('SELECT wallet,market_slug,payload FROM positions'):
  try:
   p=json.loads(raw)
   if p.get('asset')!='BTC' or p.get('duration_seconds')!=900 or p.get('state')!='PAPER_CLOSED':excluded['not_closed_btc15']+=1;continue
   if slug not in out:excluded['unverified_settlement']+=1;continue
   start,end,target,winner=out[slug]
   if None in (ts(p.get('window_start')),ts(p.get('window_end')),num(p.get('price_to_beat'))) or abs(ts(p['window_start'])-start)>1 or abs(ts(p['window_end'])-end)>1 or abs(num(p['price_to_beat'])-target)>.00001:excluded['identity_mismatch']+=1;continue
   if p.get('side') not in ('UP','DOWN'):excluded['unknown_side']+=1;continue
   positions.append((wallet,slug,p,winner))
  except (ValueError,TypeError,KeyError):excluded['malformed_position']+=1
 slugs={x[1] for x in positions};books=collections.defaultdict(list)
 for stamp,raw in db.execute('SELECT observed_at,payload FROM books ORDER BY observed_at'):
  try:
   d=json.loads(raw);m=d['market'];slug=m['market_slug']
   if slug not in slugs:continue
   start,end,target,_=out[slug]
   if not start<=stamp<end or abs(ts(m['window_start'])-start)>1 or abs(ts(m['window_end'])-end)>1 or abs(num(m['official_price_to_beat'])-target)>.00001:continue
   normalized=d['normalized'];up=num(normalized['UP'].get('market_up_probability'))
   if up is None:continue
   for side in ('UP','DOWN'):
    q=normalized.get(side) or {}
    if q.get('approved') is True:books[(slug,side)].append((stamp,up if side=='UP' else 1-up,q.get('liquidation_bids') or []))
  except (KeyError,ValueError,TypeError):continue
 result={};rules=('hold','stop2','stop3_15','stop5_30','trail')
 for rule in rules:
  c=collections.Counter();pnl=[];by_wallet=collections.defaultdict(list)
  for wallet,slug,p,winner in positions:
   status,value=evaluate(p,books.get((slug,p['side']),[]),winner,rule);c[status]+=1
   if value is not None:pnl.append(value);by_wallet[wallet].append(value)
  result[rule]={'outcomes':dict(c),'completed':len(pnl),'net':round(sum(pnl),4),'avg':round(sum(pnl)/len(pnl),5) if pnl else None,'by_wallet':{k:round(sum(v),4) for k,v in by_wallet.items()}}
 print(json.dumps({'read_only':True,'deployed':False,'verified_markets':len(out),'conflicts':conflicts,'eligible_positions':len(positions),'excluded':dict(excluded),'results':result,'warnings':['Exploratory diagnostic, NOT execution-equivalent. Missing historical entry_market_probability or gaps are not filled.','Non-hold strategies report only observed exits; incomplete paths are not treated as settlement. Compare only like-for-like complete trade cohorts.','Quote snapshot timestamps may be sparse; stop2 is observed instant only, 15s and 30s continuous stop cannot be certified without dense observations.','Profit trailing and stop priority approximated; actual engine may use more frequent marks and other rules.','Fee estimate uses 0.06*p*(1-p) for hypothetical exit, cost includes recorded entry fees.','Historical sample may overlap wallets and trades; no statistical independence or causal claim.']},indent=2))
 db.close();research.close()
if __name__=='__main__':main()
