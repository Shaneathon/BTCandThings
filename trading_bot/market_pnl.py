"""Per-wallet/per-market settlement accounting; never adds independent bankrolls."""
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from trading_bot.core import amount


def summarize(positions, streams=()):
    def empty(key):
        return dict(asset=key[0],duration_seconds=key[1],closed_trades=0,wins=0,losses=0,
                    realized_gross_pnl=Decimal(0),entry_fees=Decimal(0),realized_net_pnl=Decimal(0),
                    open_positions=0,open_cost=Decimal(0))
    groups={key:empty(key) for key in streams}
    seen=set()
    for p in positions:
        identity=(p['market_slug'],p.get('model_version'))
        if identity in seen:
            raise ValueError('Duplicate position in market report')
        seen.add(identity)
        key=(p['asset'],p['duration_seconds'])
        row=groups.setdefault(key,empty(key))
        if p['state']=='PAPER_CLOSED':
            cost,fee,payout=amount(p['cost']),amount(p['fees']),amount(p['payout'])
            net=payout-cost
            if net!=Decimal(p['pnl']):
                raise ValueError('Position P/L does not reconcile')
            row['closed_trades']+=1
            row['wins']+=int(net>0)
            row['losses']+=int(net<0)
            row['realized_net_pnl']+=net
            row['realized_gross_pnl']+=payout-(cost-fee)
            row['entry_fees']+=fee
        elif p['state']=='PAPER_OPEN':
            row['open_positions']+=1
            row['open_cost']+=amount(p['cost'])
    result=[]
    for key in sorted(groups):
        row=groups[key]
        row['market']=row['asset']+' '+str(row['duration_seconds']//60)+'m'
        row['win_rate']=row['wins']/row['closed_trades'] if row['closed_trades'] else None
        result.append({k:str(v) if isinstance(v,Decimal) else v for k,v in row.items()})
    return result


def ledger_report(path):
    # Read the entire ledger; dashboard's most recent 100 rows are not totals.
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        positions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM positions')]
        settings=db.execute('SELECT payload FROM settings WHERE id=1').fetchone()
        config=json.loads(settings[0]) if settings else {}
    return dict(ledger=Path(path).name,price_basis='HISTORICAL_FIXED_PRICE_EXPERIMENT',
                live_equivalent=False,markets=summarize(positions,streams=[(config.get('asset','BTC'),config.get('duration_seconds',900))]))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    names=['champion-directional-v1.sqlite','challenger-b-directional-v1.sqlite']
    paths=[args.state/name for name in names]
    paths+=sorted(args.state.glob('*-research-directional-v1.sqlite'))
    reports=[ledger_report(p) for p in paths if p.is_file()]
    if args.json:
        print(json.dumps(reports,indent=2))
    else:
        print('Historical fixed-price experiments; NOT live-equivalent profits.')
        print('Wallet | Market | Settled | Net P/L | Open cost')
        for report in reports:
            for row in report['markets']:
                print(report['ledger'],'|',row['market'],'|',row['closed_trades'],'|',row['realized_net_pnl'],'|',row['open_cost'])
