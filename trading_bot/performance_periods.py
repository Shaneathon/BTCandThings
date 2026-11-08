"""Read-only separation by entry-policy provenance, never by fill size."""
from decimal import Decimal
from trading_bot.market_pnl import summarize

CURRENT='OBSERVED_PAPER_V3_FIXED_150'


def period(position):
    return 'current' if (position.get('entry_limits') or {}).get('version')==CURRENT else 'earlier'


def label(position):
    version=(position.get('entry_limits') or {}).get('version')
    return {CURRENT:'$1.50 target / maximum entry policy','OBSERVED_PAPER_V2_050_5':'$0.50–$5 entry policy'}.get(version,'Earlier / untagged entry policy')


def breakdown(positions,streams=()):
    result={}
    for key in ('current','earlier','all'):
        rows=[p for p in positions if key=='all' or period(p)==key]
        closed=[p for p in rows if p.get('state')=='PAPER_CLOSED']
        opened=[p for p in rows if p.get('state')=='PAPER_OPEN']
        result[key]=dict(realized_pnl=str(sum((Decimal(p['pnl']) for p in closed),Decimal(0))),
            filled_trades=len(rows),closed_trades=len(closed),
            open_cost=str(sum((Decimal(p['cost']) for p in opened),Decimal(0))),
            market_pnl=summarize(rows,streams=streams))
    return result
