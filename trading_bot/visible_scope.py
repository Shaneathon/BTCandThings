"""Read-only presentation scope; never delete or rewrite financial records."""
from copy import deepcopy

BTC15_WALLETS=('Champion','Challenger B','BTC_15m')

def focused_snapshot(snapshot, enabled=False):
    if not enabled: return snapshot
    result=deepcopy(snapshot)
    result['portfolios']={name:report for name,report in result.get('portfolios',{}).items() if name in BTC15_WALLETS}
    result['market_portfolios']={name:report for name,report in result.get('market_portfolios',{}).items() if name in BTC15_WALLETS}
    if result.get('automatic_review'):
        result['automatic_review']['wallets']=[row for row in result['automatic_review'].get('wallets',[]) if row.get('wallet') in BTC15_WALLETS]
    health=result.get('display_health')
    if health:
        for field in ('last_filled_at','last_settled_at'):
            stamps=[r.get('activity',{}).get(field) for r in result['portfolios'].values()]
            health[field]=max((t for t in stamps if t is not None),default=None)
    return result
