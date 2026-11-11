#!/usr/bin/env python3
"""Read-only PBot performance audit. Never writes to the paper ledger."""
import argparse
from collections import defaultdict, Counter
from decimal import Decimal
import json
import sqlite3
from datetime import datetime, timezone

WALLETS = {"Champion", "Challenger B", "BTC_15m"}
def number(x):
    try: return Decimal(str(x or "0"))
    except (ValueError, TypeError, ArithmeticError): return Decimal(0)
def iso(t):
    try: return datetime.fromtimestamp(float(t), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError): return None
def group_report(rows):
    n=len(rows); wins=sum(r["pnl"]>0 for r in rows); losses=sum(r["pnl"]<0 for r in rows)
    gains=sum((r["pnl"] for r in rows if r["pnl"]>0),Decimal(0))
    lost=sum((r["pnl"] for r in rows if r["pnl"]<0),Decimal(0))
    return dict(trades=n,wins=wins,losses=losses,win_rate=round(wins/n,4) if n else None,
                pnl=round(float(gains+lost),5),average_pnl=round(float((gains+lost)/n),5) if n else None,
                avg_win=round(float(gains/wins),5) if wins else None,
                avg_loss=round(float(lost/losses),5) if losses else None,
                profit_factor=round(float(gains/-lost),3) if lost else None,
                gross_wins=round(float(gains),5),gross_losses=round(float(lost),5),
                exit_fees=round(float(sum((r["exit_fee"] for r in rows),Decimal(0))),5),
                entry_fees=round(float(sum((r["entry_fee"] for r in rows),Decimal(0))),5))
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ledger",default="/var/lib/pbot/observed-v1.sqlite")
    parser.add_argument("--details",action="store_true",help="Include per-trade data; no market IDs or wallet balances")
    args=parser.parse_args()
    db=sqlite3.connect("file:"+args.ledger+"?mode=ro",uri=True)
    db.execute("PRAGMA query_only=ON")
    trades=[]; opens=Counter(); close_reasons=defaultdict(list)
    for wallet,payload in db.execute("SELECT wallet,payload FROM positions"):
        if wallet not in WALLETS: continue
        p=json.loads(payload)
        if p.get("state")!="PAPER_CLOSED":
            if p.get("state")=="PAPER_OPEN": opens[wallet]+=1
            continue
        entry=number(p.get("entry_market_probability") or p.get("entry_price"))
        bucket=("below_25" if entry<Decimal(".25") else "25_to_49" if entry<Decimal(".50") else
                "50_to_53" if entry<Decimal(".54") else "54_to_64" if entry<=Decimal(".64") else "above_64")
        opened=p.get("opened_at");closed=p.get("closed_at")
        r=dict(wallet=wallet,policy=p.get("exit_rule") or "earlier",side=p.get("side","?"),
               entry_bucket=bucket,entry_probability=float(entry),entry_price=float(number(p.get("entry_price"))),
               exit_price=float(number(p.get("exit_price"))) if p.get("exit_price") is not None else None,
               pnl=number(p.get("pnl")),cost=number(p.get("cost")),entry_fee=number(p.get("fees")),
               exit_fee=number(p.get("exit_fees")),close_reason=p.get("close_reason","UNKNOWN"),
               opened_at=iso(opened),closed_at=iso(closed),
               held_seconds=round(float(closed)-float(opened),2) if opened and closed else None)
        trades.append(r);close_reasons[r["close_reason"]].append(r)
    def split(field):
        groups=defaultdict(list)
        for r in trades: groups[r[field]].append(r)
        return {str(k):group_report(v) for k,v in sorted(groups.items())}
    output=dict(scope="PBot paper BTC15, closed trades only",read_only=True,
                closed_trades=len(trades),open_positions=dict(opens),
                overall=group_report(trades),by_wallet=split("wallet"),by_policy=split("policy"),
                by_side=split("side"),by_entry_bucket=split("entry_bucket"),
                by_exit_reason=split("close_reason"),
                note="Different policies ran at different times; not a controlled causal comparison. PnL already includes entry and exit costs.")
    if args.details:
        output["trades"]=[{k:(round(float(v),6) if isinstance(v,Decimal) else v) for k,v in r.items()} for r in trades]
    print(json.dumps(output,indent=2,sort_keys=True))
    db.close()
if __name__=="__main__": main()
