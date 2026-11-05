"""Server-side authenticated, read-only status reader. Never redirects tokens."""
import json
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def read_status(url,token):
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
    if result.get('account',{}).get('mode')!='PAPER' or result['account'].get('live_orders_enabled') is not False:
        raise ValueError('Unexpected trading mode')
    return result
