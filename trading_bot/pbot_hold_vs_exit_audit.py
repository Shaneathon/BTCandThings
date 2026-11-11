#!/usr/bin/env python3
"""Read-only PBot actual-exit versus official-settlement counterfactual."""
import collections,json,sqlite3,math
from datetime import datetime
LEDGER="/var/lib/pbot/observed-v1.sqlite"
RESEARCH="/var/lib/private/btcandthings-research/research.sqlite"
def ro(p):
 d=sqlite3.connect("file:"+p+"?mode=ro",uri=True);d.execute("PRAGMA query_only=ON");return d
def n(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None
def t(v):
 try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).timestamp()
 except (ValueError,TypeError):return None
def summary(rows):
 if not rows:return {"positions":0}
 return {"positions":len(rows),"actual_pnl":round(sum(r[0] for r in rows),4),
 "hold_pnl":round(sum(r[1] for r in rows),4),
 "hold_minus_actual":round(sum(r[1]-r[0] for r in rows),4),
 "hold_winners":sum(r[2] for r in rows),
 "hold_losers":sum(not r[2] for r in rows)}
def main():
 research=ro(RESEARCH);db=ro(LEDGER)
 outcomes={};conflicts=set();counts=collections.Counter()
 for slug,raw in research.execute("SELECT market_slug,payload FROM evidence ORDER BY observed_at"):
  try:
   d=json.loads(raw);a=d.get("assetPriceTerms") or {}
   if d.get("status")!="MARKET_STATUS_RESOLVED" or d.get("closed") is not True:continue
   if a.get("marketType")!="ASSET_PRICE_MARKET_TYPE_UP_DOWN":continue
   if (a.get("asset") or {}).get("symbol","").lower() not in ("btc","xbt"):continue
   start,end=t(a.get("windowStart")),t(a.get("windowEnd"))
   p=a.get("priceToBeat") or {};s=a.get("settlementPrice") or {}
   target,final=n(p.get("value")),n(s.get("value"))
   if None in (start,end,target,final) or abs(end-start-900)>1 or min(target,final)<=0:continue
   if p.get("currency")!="USD" or s.get("currency")!="USD":continue
   winner="UP" if final>=target else "DOWN"
   sides=d.get("marketSides") or []
   yes=[v for v in sides if v.get("description")=="Yes" and v.get("long") is True]
   no=[v for v in sides if v.get("description")=="No" and v.get("long") is False]
   if len(yes)!=1 or len(no)!=1:continue
   if (n(yes[0].get("price")),n(no[0].get("price"))) != ((1.,0.) if winner=="UP" else (0.,1.)):continue
   identity=(start,end,round(target,5),winner)
   if slug in outcomes and outcomes[slug]!=identity:conflicts.add(slug)
   outcomes[slug]=identity
  except (ValueError,TypeError,KeyError):counts["bad_evidence"]+=1
 for slug in conflicts:outcomes.pop(slug,None)
 reasons=collections.defaultdict(list);wallets=collections.defaultdict(list);all_rows=[];stop_rows=[]
 for wallet,slug,raw in db.execute("SELECT wallet,market_slug,payload FROM positions"):
  counts["positions"]+=1
  try:
   p=json.loads(raw)
   if p.get("asset")!="BTC" or p.get("duration_seconds")!=900:
    counts["not_btc15"]+=1;continue
   if p.get("state")!="PAPER_CLOSED":
    counts["not_closed"]+=1;continue
   if slug not in outcomes:
    counts["no_verified_outcome"]+=1;continue
   start,end,target,winner=outcomes[slug]
   if None in (t(p.get("window_start")),t(p.get("window_end")),n(p.get("price_to_beat"))):
    counts["missing_identity"]+=1;continue
   if abs(t(p["window_start"])-start)>1 or abs(t(p["window_end"])-end)>1 or abs(n(p["price_to_beat"])-target)>.00001:
    counts["identity_mismatch"]+=1;continue
   side=p.get("side")
   if side not in ("UP","DOWN"):
    counts["unknown_side"]+=1;continue
   qty,cost,actual,fees=(n(p.get(k)) for k in ("quantity","cost","pnl","fees"))
   if None in (qty,cost,actual,fees) or qty<=0 or cost<0 or fees<0:
    counts["invalid_financial_fields"]+=1;continue
   # cost may include entry fees; verify from cost, entry price and fee totals.
   entry=n(p.get("entry_price"))
   if entry is None or abs(cost-qty*entry)>max(.02,.08*qty):
    counts["cost_basis_unverified"]+=1;continue
   # fees field may combine entry and exit; avoid double-counting it.
   # Use paid cost as the acquisition basis; if cost excludes fees,
   # hold result is an optimistic bound, clearly labeled.
   hold=(qty if side==winner else 0)-cost
   row=(actual,hold,side==winner)
   all_rows.append(row);wallets[wallet].append(row)
   reason=str(p.get("close_reason") or "UNKNOWN")
   reasons[reason].append(row)
   if "STOP" in reason.upper() or "ENTRY_MINUS" in reason.upper():stop_rows.append(row)
  except (ValueError,TypeError,KeyError):counts["invalid_position"]+=1
 print(json.dumps({"read_only":True,"verified_btc15_markets":len(outcomes),
 "counts":dict(counts),"matched_positions":summary(all_rows),
 "stop_reason_from_position_payload":summary(stop_rows),
 "by_wallet":{k:summary(v) for k,v in sorted(wallets.items())},
 "by_position_close_reason":{k:summary(v) for k,v in sorted(reasons.items())},
 "limitations":["Position payload may not include close_reason; UNKNOWN is not a stop classification.",
 "Cost basis and fee accounting require reconciliation before interpreting P/L difference.",
 "Hold counterfactual assumes one winning contract pays $1 and no extra settlement fees.",
 "Historical hold P/L is not an executable strategy or a forecast."]},indent=2))
 db.close();research.close()
if __name__=="__main__":main()
