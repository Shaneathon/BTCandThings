"""Shared order instructions and deterministic paper execution; no network/orders.

A future live adapter must use exchange_order(plan), and reconcile actual fills.
Verified fee/mapping references are inputs, never inferred from Yes/No labels or
feeCoefficient. This module does not activate trading on its own.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN
import hashlib
import json
from trading_bot.core import amount


QUADRATIC_TAKER_RULE = 'QUADRATIC_TAKER_PER_EXECUTION_HALF_EVEN_V1'


def taker_fee(coefficient, contracts, price):
    """Support-reported formula; coefficient applicability is a separate check.

    Call once for each execution, not once for the combined order. Aggregated
    book levels do not reveal individual counterparty executions; callers must
    disclose their simulated fill partition assumption.
    """
    c, q, p = map(amount, (coefficient, contracts, price))
    if not 0 <= c <= 1 or not Decimal('.01') <= p <= Decimal('.99'):
        raise ValueError('INVALID_TAKER_FEE_INPUT')
    return (c*q*p*(1-p)).quantize(Decimal('.01'),rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class OrderPlan:
    market_slug: str
    contract_slug: str
    strategy_version: str
    asset: str
    duration_seconds: int
    side: str
    intent: str
    quantity: str
    limit_price: str
    tick: str
    minimum_quantity: str
    created_at: float
    signal_at: float
    eligible_at: float
    expires_at: float
    window_end: float
    time_in_force: str
    mapping_evidence: str
    fee_rule: str
    fee_parameter: str
    fee_evidence: str
    execution_version: str = 'OBSERVED_DEPTH_V1'

    def validate(self):
        if (self.side not in ('UP', 'DOWN') or self.intent not in ('ORDER_INTENT_BUY_LONG', 'ORDER_INTENT_BUY_SHORT','ORDER_INTENT_SELL_LONG','ORDER_INTENT_SELL_SHORT')
                or not all(isinstance(s, str) and s for s in (self.market_slug,self.contract_slug,self.strategy_version,self.asset,
                                                             self.mapping_evidence,self.fee_evidence))):
            raise ValueError('MISSING_ORDER_IDENTITY_OR_EVIDENCE')
        expected_intents=('ORDER_INTENT_BUY_LONG','ORDER_INTENT_SELL_LONG') if self.side=='UP' else ('ORDER_INTENT_BUY_SHORT','ORDER_INTENT_SELL_SHORT')
        if self.intent not in expected_intents: raise ValueError('SIDE_INTENT_MISMATCH')
        q, p, tick, minimum = map(amount, (self.quantity,self.limit_price,self.tick,self.minimum_quantity))
        if not 0 < p < 1 or tick <= 0 or p % tick != 0 or minimum <= 0 or q < minimum or q % minimum != 0:
            raise ValueError('INVALID_TICK_OR_QUANTITY')
        import math
        if not all(type(t) in (float,int) and math.isfinite(t) for t in
                   (self.signal_at,self.created_at,self.eligible_at,self.expires_at,self.window_end)):
            raise ValueError('INVALID_ORDER_TIMES')
        if not self.signal_at <= self.created_at < self.eligible_at < self.expires_at <= self.window_end:
            raise ValueError('INVALID_ORDER_TIMING')
        if self.time_in_force not in ('TIME_IN_FORCE_FILL_OR_KILL','TIME_IN_FORCE_IMMEDIATE_OR_CANCEL'):
            raise ValueError('UNSUPPORTED_TIME_IN_FORCE')
        # Formula support does not approve a coefficient for a given market.
        if self.fee_rule not in ('VERIFIED_FLAT_PER_SHARE',QUADRATIC_TAKER_RULE) or amount(self.fee_parameter) > 1:
            raise ValueError('UNIMPLEMENTED_OR_UNVERIFIED_FEE_RULE')
        if self.execution_version != 'OBSERVED_DEPTH_V1':
            raise ValueError('UNSUPPORTED_EXECUTION_VERSION')
        return self

    @property
    def order_id(self):
        self.validate()
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()


def exchange_order(plan):
    """The same tick/size/intent/limit/TIF instructions for both adapters.

    SDK allows fractional quantities. Decimal strings are retained until an
    actual SDK boundary; there is intentionally no submission implementation.
    """
    plan.validate()
    return dict(marketSlug=plan.contract_slug,intent=plan.intent,type='ORDER_TYPE_LIMIT',
                price=dict(value=plan.limit_price,currency='USD'),quantity=plan.quantity,
                tif=plan.time_in_force,manualOrderIndicator='MANUAL_ORDER_INDICATOR_AUTOMATIC')


def simulate(plan, snapshot, now, *, participation='0.25'):
    """One IOC/FOK attempt using a validated *post-delay* snapshot of that side.

    Caller must persist the order ID exactly once before processing this result.
    Queue-based passive fills are unsupported. No fallback price, no fills before
    simulated arrival, no limit violations, no retry of an unfilled IOC/FOK.
    Snapshot must contain separately approved directional levels; raw LONG-only
    books cannot be fed directly into this function.
    """
    plan.validate()
    result = dict(order_id=plan.order_id,order=exchange_order(plan),observed_at=now,
                  state='REJECTED',filled_quantity='0',gross_cost='0',fees='0',total_cost='0',
                  fills=[],simulated_only=True,live_orders_enabled=False)
    def reject(reason):
        result['reason']=reason
        return result
    if not plan.eligible_at <= now < plan.expires_at:
        return reject('NOT_ARRIVED_OR_EXPIRED')
    if (snapshot.get('market_slug') != plan.market_slug or snapshot.get('contract_slug') != plan.contract_slug
            or snapshot.get('side') != plan.side or snapshot.get('intent') != plan.intent
            or snapshot.get('mapping_evidence') != plan.mapping_evidence
            or snapshot.get('approved') is not True):
        return reject('UNAPPROVED_OR_MISMATCHED_BOOK')
    received, requested = snapshot.get('received_at'),snapshot.get('request_started_at')
    if (type(received) not in (int,float) or type(requested) not in (int,float)
            or not plan.eligible_at <= requested <= received <= now or now-received>5
            or received-requested>5):
        return reject('NO_FRESH_POST_ARRIVAL_BOOK')
    factor = amount(participation)
    if not 0 < factor <= Decimal('.25'):
        raise ValueError('PARTICIPATION_MUST_BE_AT_MOST_25_PERCENT')
    limit, increment = amount(plan.limit_price),amount(plan.minimum_quantity)
    wanted=amount(plan.quantity)
    selling=plan.intent in ('ORDER_INTENT_SELL_LONG','ORDER_INTENT_SELL_SHORT')
    levels=snapshot.get('bids' if selling else 'offers')
    if not isinstance(levels,list) or not levels:
        return reject('NO_AVAILABLE_DEPTH')
    previous=Decimal(1) if selling else Decimal(0)
    remaining=wanted
    gross=Decimal(0)
    fee=Decimal(0)
    fills=[]
    for level in levels:
        px, visible = amount(level['price']),amount(level['quantity'])
        if not 0 < px < 1 or (px>=previous if selling else px<=previous) or visible<=0:
            return reject('INVALID_OR_DUPLICATE_BOOK_LEVEL')
        previous=px
        if (px<limit if selling else px>limit):
            continue
        available=(visible*factor/increment).to_integral_value(rounding=ROUND_DOWN)*increment
        filled=min(remaining,available)
        if filled>0:
            level_fee=(taker_fee(plan.fee_parameter,filled,px) if plan.fee_rule==QUADRATIC_TAKER_RULE
                       else filled*amount(plan.fee_parameter))
            fills.append(dict(price=str(px),quantity=str(filled),fee=str(level_fee)))
            gross+=filled*px
            fee+=level_fee
            remaining-=filled
    if remaining and plan.time_in_force=='TIME_IN_FORCE_FILL_OR_KILL':
        return reject('FOK_INSUFFICIENT_VISIBLE_DEPTH')
    if not fills:
        return reject('LIMIT_OR_DEPTH_UNFILLED')
    result['fee_partition_assumption']='ONE_SIMULATED_EXECUTION_PER_CONSUMED_PRICE_LEVEL'
    result['actual_exchange_fill_partition_known']=False
    result.update(state='FILLED' if remaining==0 else 'PARTIALLY_FILLED_CANCELLED',
                  filled_quantity=str(wanted-remaining),gross_cost=str(gross),fees=str(fee),
                  total_cost=str(gross+fee),fills=fills,reason='SIMULATED_TAKER_DEPTH')
    if selling:
        result.update(gross_cost='0',total_cost='0',gross_proceeds=str(gross),net_proceeds=str(gross-fee))
    return result
