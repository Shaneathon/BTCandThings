#!/usr/bin/env python3
"""Read-only PBot settlement source inventory; prints counts, not contract data."""
import argparse,collections,json,sqlite3
p=argparse.ArgumentParser();p.add_argument("--ledger",default="/var/lib/pbot/observed-v1.sqlite");a=p.parse_args()
db=sqlite3.connect("file:"+a.ledger+"?mode=ro",uri=True);db.execute("PRAGMA query_only=ON")
tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
result={"read_only":True,"tables":sorted(tables),"books":{},"positions":{}}
if "books" in tables:
    seen=set();statuses=collections.Counter();winners=collections.Counter();keysets=collections.Counter()
    for (raw,) in db.execute("SELECT payload FROM books"):
        try:
            data=json.loads(raw);m=data.get("market") or {};slug=m.get("market_slug")
            if not slug or slug in seen:continue
            seen.add(slug)
            statuses[str(m.get("settlement_status","MISSING"))]+=1
            winners[str(m.get("official_winner","MISSING"))]+=1
            keysets.update(m.keys())
        except (TypeError,ValueError):continue
    result["books"]={"distinct_markets":len(seen),"settlement_status_first_seen":dict(statuses),
                     "official_winner_first_seen":dict(winners),
                     "market_fields":sorted(keysets)}
if "positions" in tables:
    states=collections.Counter();reasons=collections.Counter();fields=collections.Counter()
    for (raw,) in db.execute("SELECT payload FROM positions"):
        try:
            d=json.loads(raw);states[str(d.get("state","MISSING"))]+=1
            reasons[str(d.get("close_reason","MISSING"))]+=1
            fields.update(d.keys())
        except (TypeError,ValueError):continue
    result["positions"]={"states":dict(states),"close_reasons":dict(reasons),"fields":sorted(fields)}
print(json.dumps(result,indent=2,sort_keys=True));db.close()
