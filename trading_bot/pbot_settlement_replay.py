#!/usr/bin/env python3
"""Read-only, conservative PBot BTC15 settlement-linked replay (research only).
Never modifies ledgers, orders, wallets, or deployed bot.
"""
import argparse,collections,datetime,json,sqlite3,statistics
from decimal import Decimal
def ts(s):
    try:return datetime.datetime.fromisoformat(str(s).replace("Z","+00:00")).timestamp()
    except (TypeError,ValueError):return None
def num(x):
    try:return float(x)
    except (TypeError,ValueError):return None
def first(rows):
    try:return num(rows[0]["price"]),num(rows[0]["quantity"])
    except (IndexError,KeyError,TypeError):return None,None
def open_ro(path):
    db=sqlite3.connect("file:"+path+"?mode=ro",uri=True);db.execute("PRAGMA query_only=ON");return db
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ledger",default="/var/lib/pbot/observed-v1.sqlite")
    ap.add_argument("--research",default="/var/lib/private/btcandthings-research/research.sqlite")
    a=ap.parse_args();research=open_ro(a.research);ledger=open_ro(a.ledger)
    # Require a fully resolved, corroborated outcome and exact market terms.
    outcomes={};conflicts=set();rejected=collections.Counter()
    for slug,raw in research.execute("SELECT market_slug,payload FROM evidence ORDER BY observed_at"):
        try:
            d=json.loads(raw);t=d.get("assetPriceTerms") or {}
            if d.get("status")!="MARKET_STATUS_RESOLVED" or d.get("closed") is not True:continue
            if t.get("marketType")!="ASSET_PRICE_MARKET_TYPE_UP_DOWN":continue
            if (t.get("asset") or {}).get("symbol","").lower() not in ("btc","xbt"):continue
            start,end=ts(t.get("windowStart")),ts(t.get("windowEnd"))
            if start is None or end is None or abs(end-start-900)>1:continue
            target=t.get("priceToBeat") or {};settle=t.get("settlementPrice") or {}
            if target.get("currency")!="USD" or settle.get("currency")!="USD":continue
            target_price=num(target.get("value"));final=num(settle.get("value"))
            if target_price is None or final is None or min(target_price,final)<=0:continue
            winner="UP" if final>=target_price else "DOWN"
            sides=d.get("marketSides") or []
            yes=[s for s in sides if s.get("description")=="Yes" and s.get("long") is True]
            no=[s for s in sides if s.get("description")=="No" and s.get("long") is False]
            if len(yes)!=1 or len(no)!=1:rejected["missing_side_confirmation"]+=1;continue
            yp=num(yes[0].get("price"));np=num(no[0].get("price"))
            if (yp,np) not in ((1.,0.),(0.,1.)) or ((yp==1.)!=(winner=="UP")):
                rejected["side_disagreement"]+=1;continue
            identity=(start,end,round(target_price,5),winner)
            if slug in outcomes and outcomes[slug]!=identity:conflicts.add(slug)
            outcomes[slug]=identity
        except (ValueError,TypeError,KeyError):rejected["malformed_evidence"]+=1
    for slug in conflicts:outcomes.pop(slug,None)
    markets=collections.defaultdict(list);issues=collections.Counter()
    for observed,raw in ledger.execute("SELECT observed_at,payload FROM books ORDER BY observed_at"):
        try:
            d=json.loads(raw);m=d["market"];slug=m["market_slug"]
            if m.get("asset")!="BTC" or m.get("duration_seconds")!=900:continue
            if slug not in outcomes:continue
            start,end,target,winner=outcomes[slug]
            if abs(ts(m["window_start"])-start)>1 or abs(ts(m["window_end"])-end)>1 or abs(num(m["official_price_to_beat"])-target)>.00001:
                issues["identity_mismatch"]+=1;continue
            if not start<=observed<end:continue
            books=d["normalized"]
            if any(books[s].get("approved") is not True for s in ("UP","DOWN")):continue
            mark=num(books["UP"].get("market_up_probability"))
            if mark is None:continue
            q={}
            for s in ("UP","DOWN"):
                ask,aq=first(books[s].get("offers") or [])
                bid,bq=first(books[s].get("liquidation_bids") or [])
                if None in (ask,aq,bid,bq) or min(aq,bq)<1 or not 0<bid<=ask<1:break
                q[s]=(ask,bid,aq,bq)
            if len(q)!=2:continue
            markets[slug].append((observed,mark,q))
        except (ValueError,TypeError,KeyError,IndexError):issues["invalid_book"]+=1
    # Chronological split by market window, no tuning on held-out markets.
    eligible=sorted((outcomes[slug][0],slug) for slug,rows in markets.items() if len(rows)>=3)
    split=int(len(eligible)*.7);train={slug for _,slug in eligible[:split]};test={slug for _,slug in eligible[split:]}
    # Flat one-contract fee estimate: published quadratic taker coefficient 0.06
    # fee=0.06*p*(1-p), per side; estimate, not exact exchange rounding.
    def fee(p):return .06*p*(1-p)
    def simulate(slug,side,threshold,stop,hold,target):
        rows=markets[slug];start,end,beat,winner=outcomes[slug];prev=None;entry=None
        for i,(t,mark,q) in enumerate(rows):
            prob=mark if side=="UP" else 1-mark
            if prev is not None and t-prev[0]<=15 and prev[1]<threshold<=prob and 90<=t-start<=660:
                ask,bid,aq,bq=q[side]
                if ask-bid<=.02 and aq>=1:entry=i;break
            prev=(t,prob)
        if entry is None:return None
        entered,_,quotes=rows[entry];ask=quotes[side][0]
        # Incomplete observed quote paths cannot establish a stop/target did not occur.
        # Keep settlement as a separate buy-and-hold counterfactual, never impute it as
        # the strategy exit when the last quote precedes settlement.
        last=rows[-1][0]
        since=None;previous_t=entered
        for t,mark,q in rows[entry+1:]:
            if t-previous_t>15:since=None
            previous_t=t
            prob=mark if side=="UP" else 1-mark
            bid=q[side][1]
            if prob>=target and q[side][3]>=1:
                return ("target",bid-fee(bid)-ask-fee(ask))
            if prob<=threshold-stop:
                if since is None:since=t
                if t-since>=hold and q[side][3]>=1:
                    return ("stop",bid-fee(bid)-ask-fee(ask))
            else:since=None
        if end-last>60:return ("unresolved",None)
        return ("settlement",float(winner==side)-ask-fee(ask))
    scenarios=[]
    for side in ("UP","DOWN"):
        for threshold in (.20,.35,.45,.54,.58,.62,.70):
            for stop,hold in ((.03,15),(.05,30),(.07,30)):
                for target in (.70,.75):
                    row=dict(side=side,entry=threshold,stop=stop,hold=hold,target=target)
                    for name,slugs in (("train",train),("holdout",test)):
                        pnls=[];counts=collections.Counter()
                        for slug in slugs:
                            result=simulate(slug,side,threshold,stop,hold,target)
                            if result is None:continue
                            reason,pnl=result;counts[reason]+=1
                            if pnl is not None:pnls.append(pnl)
                        row[name]=dict(entries=sum(counts.values()),complete=len(pnls),unresolved=counts["unresolved"],
                            stop=counts["stop"],target=counts["target"],settlement=counts["settlement"],
                            net_per_one_contract=round(sum(pnls),5),avg_net_per_one_contract=round(statistics.mean(pnls),5) if pnls else None)
                    scenarios.append(row)
    scenarios.sort(key=lambda r:(-r["train"]["complete"],r["train"]["unresolved"],r["side"],r["entry"]))
    print(json.dumps(dict(read_only=True,not_deployed=True,method="One contract per market; observed crossing, ask entry, bid exits, approximate 0.06*p*(1-p) taker fee per fill; observed stop/target exits count even if later quotes end early; otherwise unresolved if no quote within final 60 seconds; no lean or slippage modeling; not execution-equivalent.",
        evidence=dict(verified_markets=len(outcomes),conflicts=len(conflicts),rejected=dict(rejected)),
        books=dict(matched_markets=len(markets),eligible_markets=len(eligible),training_markets=len(train),held_out_markets=len(test),issues=dict(issues)),
        warning="Incomplete quote paths are unresolved, not losses or wins. Observed exits may be biased toward early stops/targets; no strategy ranking is reliable until continuous coverage, lean, fill size and fees are validated. Never deploy based on these rankings.",
        scenarios=len(scenarios),most_observed_scenarios=scenarios[:12],all_scenarios=scenarios),indent=2))
    research.close();ledger.close()
if __name__=="__main__":main()
