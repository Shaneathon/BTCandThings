"""Server-side authenticated, read-only status reader. Never redirects tokens."""
import json
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def read_status(url,token,expected_venue="Polymarket US"):
    parsed=urlsplit(url)
    loopback=parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')
    if ((parsed.scheme!='https' and not loopback) or not parsed.hostname or parsed.username or parsed.password
            or parsed.path!='/status' or parsed.query or parsed.fragment or len(token)<32):
        raise ValueError('Configure an authenticated HTTPS /status endpoint')
    request=Request(url,headers={'Authorization':'Bearer '+token},method='GET')
    with build_opener(NoRedirect()).open(request,timeout=5) as response:
        raw=response.read(4_000_001)
        if len(raw)>4_000_000:
            raise ValueError('Oversized status response')
        result=json.loads(raw)
    if result.get('account',{}).get('venue')!=expected_venue or result.get('account',{}).get('mode')!='PAPER' or result['account'].get('live_orders_enabled') is not False:
        raise ValueError('Unexpected trading mode')
    return result


def read_trades(url,token,wallet='*',page=1,as_of=None):
    """Derive only the authenticated /trades route from a valid status origin."""
    from urllib.parse import urlencode,urlunsplit
    parsed=urlsplit(url)
    local=parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')
    if ((parsed.scheme!='https' and not local) or not parsed.hostname or parsed.username or parsed.password
            or parsed.path!='/status' or parsed.query or parsed.fragment or len(token)<32):
        raise ValueError('Configure an authenticated HTTPS /status origin')
    query=dict(wallet=wallet,page=str(page),limit='50')
    if as_of is not None: query['as_of']=str(as_of)
    target=urlunsplit((parsed.scheme,parsed.netloc,'/trades',urlencode(query),''))
    request=Request(target,headers={'Authorization':'Bearer '+token},method='GET')
    with build_opener(NoRedirect()).open(request,timeout=5) as response:
        raw=response.read(4_000_001)
        if len(raw)>4_000_000: raise ValueError('Oversized trade history response')
        data=json.loads(raw)
    if (data.get('account',{}).get('venue')!='Polymarket US' or data['account'].get('mode')!='PAPER'
            or data['account'].get('live_orders_enabled') is not False or not isinstance(data.get('trades'),list)
            or data.get('wallet')!=wallet):
        raise ValueError('Unexpected history source')
    return data
