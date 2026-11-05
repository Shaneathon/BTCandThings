"""Offline settlement P/L with explicit quotes, fees and slippage. No orders."""
import argparse
import json
import math
from pathlib import Path
import sqlite3
from collector import epoch


def number(value, lower=0, upper=None):
    if isinstance(value,bool):
        raise ValueError('Boolean is not a price or quantity')
    result=float(value)
    if not math.isfinite(result) or result<lower or (upper is not None and result>upper):
        raise ValueError('Invalid simulation number')
    return result


def simulate(markets, predictions, quotes, quantity, fee_per_share, slippage_per_share, max_quote_delay=30):
    quantity=number(quantity,lower=.000001)
    fee=number(fee_per_share)
    slip=number(slippage_per_share)
    delay=number(max_quote_delay)
    windows={m['market_slug']:m for m in markets}
    selected={}
    # Earliest observed prediction per model/market, never choose the winner
    # retrospectively. Invalid first observations remain explicit skipped cases.
    for prediction in sorted(predictions,key=lambda p:epoch(p['recorded_at'])):
        selected.setdefault((prediction['market_slug'],prediction['model_version']),prediction)
    trades=[]
    for (slug,model),p in sorted(selected.items()):
        result=dict(market_slug=slug,model_version=model,state='SKIPPED',simulated_only=True)
        trades.append(result)
        try:
            m=windows[slug]
            if m['settlement_status']!='VERIFIED' or m.get('official_winner') not in ('UP','DOWN') or not m.get('settlement_evidence'):
                raise ValueError('Official settlement pending')
            prediction_time=epoch(p['recorded_at'])
            if not epoch(m['window_start'])<=prediction_time<epoch(m['window_end']):
                raise ValueError('Prediction outside market window')
            if epoch(p['source_timestamp'])>prediction_time:
                raise ValueError('Prediction uses future source data')
            probability=number(p['predicted_up_probability'],upper=1)
            if probability==.5 or p.get('lean_direction')=='NEUTRAL':
                raise ValueError('No directional entry')
            side='UP' if probability>.5 else 'DOWN'
            candidates=[]
            for q in quotes:
                if q.get('market_slug')!=slug or q.get('contract_slug')!=m['contract_slug']:
                    continue
                captured=epoch(q['captured_at'])
                if prediction_time<=captured<=prediction_time+delay and captured<epoch(m['window_end']):
                    # Semantic side labels must already be verified by the
                    # source adapter; positional 0/1 mappings are forbidden.
                    if q.get('side_mapping_verified') is True and q.get('source_name')=='Polymarket US':
                        candidates.append(q)
            if not candidates:
                raise ValueError('No timely verified executable quote')
            quote=min(candidates,key=lambda q:epoch(q['captured_at']))
            ask=number(quote[side.lower()+'_ask'],upper=1)
            if ask+slip>1:
                raise ValueError('Slippage exceeds contract price range')
            entry=ask+slip
            payout=1 if side==m['official_winner'] else 0
            result.update(state='SIMULATED_CLOSED',side=side,entry_at=quote['captured_at'],
                          entry_price=entry,quantity=quantity,estimated_fees=fee*quantity,
                          estimated_slippage=slip*quantity,exit_price=payout,
                          realized_pnl=round(quantity*(payout-entry-fee),10))
        except (ValueError,KeyError,TypeError,OverflowError) as exc:
            result['reason']=str(exc) if isinstance(exc,ValueError) else 'Incomplete simulation inputs'
    closed=[t for t in trades if t['state']=='SIMULATED_CLOSED']
    return dict(trades=trades,closed=len(closed),skipped=len(trades)-len(closed),
                realized_pnl=round(sum(t['realized_pnl'] for t in closed),10),
                simulated_only=True,assumptions=dict(quantity=quantity,fee_per_share=fee,
                slippage_per_share=slip,max_quote_delay_seconds=delay),
                limitation='No liquidity/depth fills or capital-constrained portfolio simulation. Not real trading.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--quotes',type=Path,required=True,help='Reviewed normalized executable-quote JSON list')
    parser.add_argument('--quantity',type=float,required=True)
    parser.add_argument('--fee-per-share',type=float,required=True)
    parser.add_argument('--slippage-per-share',type=float,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    with sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True) as db:
        markets=[json.loads(r[0]) for r in db.execute("SELECT payload FROM records WHERE kind='market'")]
        predictions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM research_snapshots')]
    quotes=json.loads(args.quotes.read_text())
    if not isinstance(quotes,list):
        parser.error('Quotes must be a reviewed JSON list')
    report=simulate(markets,predictions,quotes,args.quantity,args.fee_per_share,args.slippage_per_share)
    with args.out.open('x') as output:
        json.dump(report,output,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps({k:v for k,v in report.items() if k!='trades'}))


if __name__=='__main__':
    main()
