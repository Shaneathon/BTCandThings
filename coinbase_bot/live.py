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
