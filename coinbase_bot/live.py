"""Coinbase Advanced order-payload preparation; submission intentionally absent."""
from coinbase_bot.market_data import PRODUCTS,positive


class LiveTradingDisabled(RuntimeError): pass


def prepare_limit_order(product,side,quantity,limit_price,client_order_id):
    if product not in PRODUCTS or side not in ('BUY','SELL') or not isinstance(client_order_id,str) or not client_order_id:
        raise ValueError('Explicit product, spot side and durable client ID required')
    return dict(client_order_id=client_order_id,product_id=product,side=side,
                order_configuration={'limit_limit_gtc':{'base_size':str(positive(quantity)),
                                                      'limit_price':str(positive(limit_price)),'post_only':False}})


def submit(*args,**kwargs):
    raise LiveTradingDisabled('Coinbase real submission is not implemented or authorized in this paper release')


def observed_order(proposal):
    """Return the exact frozen paper instruction for a future SDK adapter.

    Does not submit, preview or contact Coinbase. The source plan and execution
    configuration must be validated before any future live implementation.
    """
    import copy
    order=copy.deepcopy(proposal['order'])
    if (order.get('product_id') not in PRODUCTS or order.get('side') not in ('BUY','SELL')
            or not order.get('client_order_id') or set(order.get('order_configuration',{}))!={'limit_limit_fok'}):
        raise ValueError('Expected frozen, identified FOK spot order')
    terms=order['order_configuration']['limit_limit_fok']
    positive(terms['base_size']);positive(terms['limit_price'])
    return order
