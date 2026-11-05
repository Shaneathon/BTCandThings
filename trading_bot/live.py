"""Live-order preparation only. Submission is intentionally unavailable."""
from trading_bot.core import amount


class LiveTradingDisabled(RuntimeError):
    pass


def build_limit_order(position,mapping):
    """SDK 2.4.1-compatible intent; never infer LONG/SHORT from array order."""
    if (mapping.get('contract_slug')!=position['contract_slug'] or not mapping.get('evidence')
            or mapping.get('verified') is not True):
        raise ValueError('Reviewed contract-specific side mapping required')
    if {mapping.get('up_buy_intent'),mapping.get('down_buy_intent')} != {'ORDER_INTENT_BUY_LONG','ORDER_INTENT_BUY_SHORT'}:
        raise ValueError('Distinct reviewed UP and DOWN intents required')
    intent=mapping.get(position['side'].lower()+'_buy_intent')
    if intent not in ('ORDER_INTENT_BUY_LONG','ORDER_INTENT_BUY_SHORT'):
        raise ValueError('Unsupported mapped order intent')
    price=amount(position['entry_price'])
    quantity=amount(position['quantity'])
    if not 0<price<=1 or quantity<1 or quantity!=quantity.to_integral_value():
        raise ValueError('Invalid limit order')
    return dict(marketSlug=position['contract_slug'],intent=intent,type='ORDER_TYPE_LIMIT',
                price={'value':str(price),'currency':'USD'},quantity=int(quantity),
                tif='TIME_IN_FORCE_FILL_OR_KILL',manualOrderIndicator='MANUAL_ORDER_INDICATOR_AUTOMATIC')


class LiveGateway:
    def preview(self,client,position,mapping):
        """Explicit injected authenticated SDK preview, never called by paper code."""
        return client.orders.preview({'request':build_limit_order(position,mapping)})

    def submit(self,*args,**kwargs):
        raise LiveTradingDisabled('Real orders require a separately implemented, reviewed and explicitly authorized execution release')
