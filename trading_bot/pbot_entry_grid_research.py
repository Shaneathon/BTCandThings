#!/usr/bin/env python3
"""Read-only coverage diagnostic and entry-grid experiment on archived PBot books.

Research ONLY. Uses recorded executable offers and bids where present. No trades
are placed; no ledger is modified. Report gaps instead of filling them in.
"""
import argparse, collections, json, sqlite3
from datetime import datetime,timezone

def val(x):
    try: return float(x)
    except (TypeError,ValueError): return None
def price(level):
    return val(level.get("price")) if isinstance(level,dict) else None
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",default="/var/lib/pbot/observed-v1.sqlite")
    p.add_argument("--max-books",type=int,default=300000)
    args=p.parse_args()
    db=sqlite3.connect("file:"+args.ledger+"?mode=ro",uri=True)
    db.execute("PRAGMA query_only=ON")
    summary=collections.Counter();markets=collections.defaultdict(list)
    for ts,raw in db.execute("SELECT observed_at,payload FROM books ORDER BY observed_at DESC LIMIT ?",(args.max_books,)):
        summary["archived_books"]+=1
        try:
            b=json.loads(raw);m=b["market"];q=b["normalized"];slug=m["market_slug"]
            if m.get("asset")!="BTC" or m.get("duration_seconds")!=900: continue
            end=datetime.fromisoformat(m["window_end"].replace("Z","+00:00")).timestamp()
            start=datetime.fromisoformat(m["window_start"].replace("Z","+00:00")).timestamp()
            if not start<=ts<end: continue
            up=q["UP"];dn=q["DOWN"]
            mark=val(up.get("market_up_probability"))
            if mark is None: summary["missing_market_mark"]+=1;continue
            offers={};bids={}
            for side,book in (("UP",up),("DOWN",dn)):
                if book.get("approved") is not True: break
                offers[side]=price((book.get("offers") or [{}])[0])
                bids[side]=price((book.get("liquidation_bids") or [{}])[0])
            if len(offers)!=2 or any(x is None for x in list(offers.values())+list(bids.values())):
                summary["missing_executable_quote"]+=1;continue
            markets[slug].append((ts,ts-start,mark,offers,bids))
            summary["usable_books"]+=1
        except (KeyError,ValueError,TypeError,IndexError,OverflowError):
            summary["unparseable_books"]+=1
    thresholds=[.10,.15,.20,.25,.30,.35,.40,.45,.50,.54,.56,.58,.60,.62,.64,.70]
    stops=[.02,.03,.05,.07,.10]
    holds=[0,15,30,45,60]
    results=[]
    for threshold in thresholds:
        for direction in ("UP","DOWN"):
            for stop in stops:
                for hold in holds:
                    opportunities=0;exits=0;unresolved=0;missing_stop_coverage=0
                    gross_proxy=0.0
                    for ticks in markets.values():
                        ticks.sort(key=lambda x:x[0])
                        previous=None;entry=None
                        for t in ticks:
                            prob=t[2] if direction=="UP" else 1-t[2]
                            if previous and 0<t[0]-previous[0]<=5 and previous[1]<threshold<=prob and 90<=t[1]<=720:
                                ask=t[3][direction]
                                bid=t[4][direction]
                                if ask is not None and bid is not None and ask-bid<=.02:
                                    entry=t;break
                            previous=(t[0],prob)
                        if entry is None: continue
                        opportunities+=1
                        since=None;last=None;triggered=False
                        for t in ticks:
                            if t[0]<=entry[0]:continue
                            prob=t[2] if direction=="UP" else 1-t[2]
                            if last is not None and t[0]-last>5: since=None
                            last=t[0]
                            if prob<=threshold-stop:
                                if since is None:since=t[0]
                                if t[0]-since>=hold:
                                    gross_proxy+=t[4][direction]-entry[3][direction]
                                    exits+=1;triggered=True;break
                            else:since=None
                        if not triggered:
                            unresolved+=1
                            if last is None:missing_stop_coverage+=1
                    results.append(dict(entry=threshold,side=direction,stop_points=stop,hold_seconds=hold,
                                        observed_entries=opportunities,stop_exits=exits,
                                        unresolved=unresolved,unresolved_no_followup=missing_stop_coverage,
                                        observed_stop_exit_gross_price_difference=round(gross_proxy,5)))
    results.sort(key=lambda r:(-r["observed_entries"],r["entry"],r["side"],r["stop_points"],r["hold_seconds"]))
    print(json.dumps(dict(read_only=True,scope="BTC 15m archived books",books=dict(summary),
        distinct_markets=len(markets),candidate_combinations=len(results),
        IMPORTANT="NOT A PROFIT BACKTEST: results omit fee, settlement and unobserved exit paths; sparse quotes and no lean matching cause selection bias. Gross price differences only for observed stop exits. Do not rank strategies by this proxy.",
        most_observed_candidates=results[:30],
        coverage_by_entry=[dict(entry=x,side=d,max_observed_entries=max((r["observed_entries"] for r in results if r["entry"]==x and r["side"]==d),default=0)) for x in thresholds for d in ("UP","DOWN")]),indent=2))
    db.close()
if __name__=="__main__":main()
