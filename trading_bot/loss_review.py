"""Read-only current-policy paper fill review; no network calls or rule changes."""
import argparse
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from trading_bot.performance_periods import period


def inspect(ledger,source):
    official={}
    with sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True) as db:
        for key,encoded in db.execute("SELECT key,payload FROM records WHERE kind='market'"):
            official[key]=json.loads(encoded)
    groups=defaultdict(list);examples=[]
    with sqlite3.connect(Path(ledger).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        for wallet,slug,encoded,order in db.execute('SELECT p.wallet,p.market_slug,p.payload,o.payload FROM positions p LEFT JOIN orders o ON p.wallet=o.wallet AND p.market_slug=o.market_slug'):
            p=json.loads(encoded)
            if period(p)!='current' or p.get('state')!='PAPER_CLOSED': continue
            o=json.loads(order) if order else {};signal=o.get('signal',{});plan=o.get('plan',{})
            q=Decimal(p['quantity']);cost=Decimal(p['cost']);fee=Decimal(p['fees']);pnl=Decimal(p['pnl']);payout=Decimal(p['payout'])
            probability=signal.get('predicted_up_probability')
            probability=Decimal(str(probability)) if probability is not None else None
            chosen_probability=(probability if p['side']=='UP' else 1-probability) if probability is not None else None
            m=official.get(slug,{})
            checks=[]
            if not o: checks.append('MISSING_ORDER')
            if payout-cost!=pnl: checks.append('PNL_MISMATCH')
            if m.get('settlement_status')!='VERIFIED': checks.append('OFFICIAL_RECORD_UNAVAILABLE_OR_UNVERIFIED')
            else:
                expected=q if m.get('official_winner')==p['side'] else Decimal(0)
                if payout!=expected: checks.append('PAYOUT_WINNER_MISMATCH')
                if p['contract_slug']!=m.get('contract_slug'): checks.append('CONTRACT_MISMATCH')
                if Decimal(str(m['official_price_to_beat']))!=Decimal(p['price_to_beat']): checks.append('TARGET_MISMATCH')
            if probability is not None and p['side']!=('UP' if probability>Decimal('.5') else 'DOWN'): checks.append('SIGNAL_DIRECTION_MISMATCH')
            record=dict(wallet=wallet,market=slug,side=p['side'],entry_price=str(p['entry_price']),
                cost=str(cost),fees=str(fee),net_pnl=str(pnl),chosen_signal_probability=str(chosen_probability) if chosen_probability is not None else None,
                break_even_probability=str(cost/q),winning_claim=payout>0,official_winner=m.get('official_winner'),checks=checks,
                seconds_remaining_at_proposal=round(p['window_end']-plan['created_at'],1) if plan.get('created_at') else None)
            groups[wallet].append(record)
            if checks or pnl<0: examples.append(record)
    summaries=[]
    for wallet,rows in sorted(groups.items()):
        probabilities=[Decimal(r['chosen_signal_probability']) for r in rows if r['chosen_signal_probability'] is not None]
        summaries.append(dict(wallet=wallet,settled_positions=len(rows),winning_claims=sum(r['winning_claim'] for r in rows),
            net_winning_positions=sum(Decimal(r['net_pnl'])>0 for r in rows),
            net_pnl=str(sum((Decimal(r['net_pnl']) for r in rows),Decimal(0))),fees=str(sum((Decimal(r['fees']) for r in rows),Decimal(0))),
            average_chosen_signal_probability=str(sum(probabilities)/len(probabilities)) if probabilities else None,
            average_entry_price=str(sum(Decimal(r['entry_price']) for r in rows)/len(rows)),
            average_break_even_probability=str(sum(Decimal(r['break_even_probability']) for r in rows)/len(rows)),
            check_failures=sum(bool(r['checks']) for r in rows),
            directions={side:dict(positions=len(part),winning_claims=sum(r['winning_claim'] for r in part),
                net_pnl=str(sum((Decimal(r['net_pnl']) for r in part),Decimal(0)))) for side in ('UP','DOWN') if (part:=[r for r in rows if r['side']==side])}))
    return dict(policy='Current $1.50-target entries only',wallets=summaries,
        integrity_findings=[r for r in examples if r['checks']],
        largest_net_losses=sorted(examples,key=lambda r:Decimal(r['net_pnl']))[:12],
        note='Read-only. Signal probabilities are model estimates, not established accuracy. Filled-trade selection differs from all tracker forecasts. Shared market windows are correlated. No live-profitability claim.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,default=Path('/var/lib/pbot/observed-v1.sqlite'))
    parser.add_argument('--source',type=Path,default=Path('/var/lib/btcandthings-research/research.sqlite'))
    args=parser.parse_args();print(json.dumps(inspect(args.ledger,args.source),indent=2))
