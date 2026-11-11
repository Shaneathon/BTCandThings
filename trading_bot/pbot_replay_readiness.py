#!/usr/bin/env python3
"""PBot replay readiness: read-only audit of market outcomes and quote coverage.

No strategy ranking until final outcomes, execution costs and market continuity
are established. Does not change trading, wallets, or SQLite schema.
"""
import argparse,collections,datetime,json,sqlite3,statistics

def epoch(x):
    try:return datetime.datetime.fromisoformat(str(x).replace("Z","+00:00")).timestamp()
    except (ValueError,TypeError):return None
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ledger",default="/var/lib/pbot/observed-v1.sqlite")
    args=ap.parse_args()
    db=sqlite3.connect("file:"+args.ledger+"?mode=ro",uri=True)
    db.execute("PRAGMA query_only=ON")
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    counts={t:db.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in
            ("books","positions","evidence","predictions","lean_observations","market_entry_marks") if t in tables}
    markets=collections.defaultdict(list);first_metadata={}
    if "books" in tables:
        for ts,raw in db.execute("SELECT observed_at,payload FROM books ORDER BY observed_at"):
            try:
                data=json.loads(raw);m=data["market"]
                if m.get("asset")!="BTC" or m.get("duration_seconds")!=900:continue
                start,end=epoch(m["window_start"]),epoch(m["window_end"])
                if start is None or end is None or not start<=ts<end:continue
                normalized=data["normalized"];up=normalized["UP"];dn=normalized["DOWN"]
                mark=up.get("market_up_probability")
                if mark is None:continue
                def level(book,field):
                    rows=book.get(field) or []
                    return float(rows[0]["price"]) if rows else None
                prices={side:{"ask":level(normalized[side],"offers"),
                              "bid":level(normalized[side],"liquidation_bids")}
                        for side in ("UP","DOWN")}
                if any(v is None for x in prices.values() for v in x.values()):continue
                markets[m["market_slug"]].append((ts,start,end,float(mark),prices))
                first_metadata.setdefault(m["market_slug"],m)
            except (KeyError,TypeError,ValueError,IndexError):continue
    durations=[];max_gaps=[];spreads=[];segments=collections.Counter()
    for slug,rows in markets.items():
        durations.append(rows[-1][0]-rows[0][0])
        gaps=[b[0]-a[0] for a,b in zip(rows,rows[1:])]
        max_gaps.append(max(gaps) if gaps else 0)
        for ts,start,end,mark,p in rows:
            segments[int((ts-start)//60)]+=1
            spreads.append(p["UP"]["ask"]-p["UP"]["bid"])
    resolved=collections.Counter();evidence_shapes=collections.Counter()
    if "evidence" in tables:
        columns=[r[1] for r in db.execute("PRAGMA table_info(evidence)")]
        evidence_shapes["columns"] = columns
        if "payload" in columns:
            for (raw,) in db.execute("SELECT payload FROM evidence"):
                try:
                    d=json.loads(raw);terms=d.get("assetPriceTerms") or {}
                    if terms.get("marketType")!="ASSET_PRICE_MARKET_TYPE_UP_DOWN":continue
                    if (terms.get("asset") or {}).get("symbol") not in ("btc","xbt"):continue
                    status=d.get("status")
                    if status=="MARKET_STATUS_RESOLVED" and d.get("closed") is True:
                        target=terms.get("priceToBeat") or {};settled=terms.get("settlementPrice") or {}
                        if target.get("value") is not None and settled.get("value") is not None:
                            resolved["resolved_with_target_and_settlement"]+=1
                        else:resolved["resolved_missing_numeric_outcome"]+=1
                    else:resolved["not_resolved"]+=1
                except (ValueError,TypeError):resolved["invalid_evidence_payload"]+=1
    def pct(values,p):
        if not values:return None
        s=sorted(values);return round(s[min(len(s)-1,int((len(s)-1)*p))],2)
    print(json.dumps(dict(read_only=True,table_counts=counts,archived_btc15_markets=len(markets),
        quote_coverage=dict(median_span_seconds=pct(durations,.5),p90_span_seconds=pct(durations,.9),
          median_max_gap_seconds=pct(max_gaps,.5),p90_max_gap_seconds=pct(max_gaps,.9),
          median_up_spread=pct(spreads,.5),p90_up_spread=pct(spreads,.9),
          quote_counts_by_minute=dict(sorted(segments.items()))),
        settlement_evidence=dict(resolved),evidence_table_shape=dict(evidence_shapes),
        assessment="Readiness diagnostic only. Outcome join by market identity, chronological held-out tests, lean confirmation, liquidity and fee simulation must precede strategy profitability claims."),indent=2))
    db.close()
if __name__=="__main__":main()
