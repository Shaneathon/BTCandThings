"""Read-only separation by entry-policy provenance, never by fill size."""
from decimal import Decimal
from trading_bot.market_pnl import summarize

CURRENT='OBSERVED_PAPER_V5_MARKET_BAND'


def period(position,current_version=CURRENT):
    return 'current' if (position.get('entry_limits') or {}).get('version')==current_version else 'earlier'


def label(position):
    version=(position.get('entry_limits') or {}).get('version')
    return {CURRENT:'54–64% market band / fixed 2-point stop / 71% target','OBSERVED_PAPER_V4_TRAILING_150':'All-window entries / model-probability trailing exits', 'OBSERVED_PAPER_V3_FIXED_150':'$1.50 prior entry policy','OBSERVED_PAPER_V2_050_5':'$0.50–$5 entry policy'}.get(version,'Earlier / untagged entry policy')


def breakdown(positions,streams=(),current_version=CURRENT):
    result={}
    for key in ('current','earlier','all'):
        rows=[p for p in positions if key=='all' or period(p,current_version)==key]
        closed=[p for p in rows if p.get('state')=='PAPER_CLOSED']
        opened=[p for p in rows if p.get('state')=='PAPER_OPEN']
        result[key]=dict(realized_pnl=str(sum((Decimal(p['pnl']) for p in closed),Decimal(0))),
            filled_trades=len(rows),closed_trades=len(closed),
            open_cost=str(sum((Decimal(p['cost']) for p in opened),Decimal(0))),
            market_pnl=summarize(rows,streams=streams))
    return result
