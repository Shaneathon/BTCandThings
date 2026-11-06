"""Pure paper-research cost calculations; not live quotes or fee schedules."""
from decimal import Decimal


def number(value):
    if isinstance(value,bool): raise ValueError('Boolean is not an amount')
    result=Decimal(str(value))
    if not result.is_finite(): raise ValueError('Finite value required')
    return result


def binary_ev(probability, ask, fee_per_share, slippage_per_share):
    p,a,fee,slip=map(number,(probability,ask,fee_per_share,slippage_per_share))
    if not 0<=p<=1 or not 0<a<=1 or fee<0 or slip<0:
        raise ValueError('Invalid binary probability, price or costs')
    cost=a+fee+slip
    return dict(cost_per_share=cost,expected_net_per_share=p-cost,
                expected_return_on_cost=p/cost-1,break_even_win_probability=cost)


def spot_break_even_move(buy_fee,sell_fee,buy_slippage,sell_slippage):
    bf,sf,bs,ss=map(number,(buy_fee,sell_fee,buy_slippage,sell_slippage))
    if not all(0<=value<1 for value in (bf,sf,bs,ss)):
        raise ValueError('Rates must be between zero inclusive and one exclusive')
    return (1+bf)*(1+bs)/((1-sf)*(1-ss))-1


if __name__=='__main__':
    print('Hypothetical 95% probability at 98c + 2c costs:',binary_ev('.95','.98','.01','.01'))
    print('Spot break-even exit-bid increase over entry ask at current assumed costs:',
          str(100*spot_break_even_move('.006','.006','.0005','.0005'))+'%')
