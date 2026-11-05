"""Read-only per-asset cloud performance. No BTC history substitution."""
import json
import math
from datetime import datetime
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


def reader(url,key):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment or not key:
        raise ValueError('Cloud history not configured')
    def get(table,params):
        if table not in ('asset_market_windows','asset_market_predictions'):
            raise ValueError('Only research history reads allowed')
        headers={'apikey':key}
        if not key.startswith('sb_secret_'):
            headers['Authorization']='Bearer '+key
        req=Request(url.rstrip('/')+'/rest/v1/'+table+'?'+urlencode(params),headers=headers,method='GET')
        with build_opener(NoRedirect()).open(req,timeout=8) as response:
            raw=response.read(4_000_001)
            if len(raw)>4_000_000:
                raise ValueError('Oversized history response')
            return json.loads(raw)
    return get


def timestamp(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone required')
    return parsed.timestamp()


def summarize(markets,predictions,asset,seconds):
    outcomes={m['market_slug']:m for m in markets if m.get('asset')==asset and m.get('duration_seconds')==seconds
              and m.get('settlement_status')=='VERIFIED' and m.get('official_winner') in ('UP','DOWN')
              and m.get('settlement_evidence')}
    selected={}
    invalid=0
    for row in predictions:
        m=outcomes.get(row.get('market_slug'))
        if not m:
            continue
        try:
            p=float(row['predicted_up_probability'])
            when=timestamp(row['recorded_at'])
            source=timestamp(row['source_timestamp'])
            if not math.isfinite(p) or not 0<=p<=1 or source>when or not timestamp(m['window_start'])<=when<timestamp(m['window_end']):
                raise ValueError('Invalid archived prediction')
            key=(row['market_slug'],row['model_version'])
            if key not in selected or when<selected[key][0]:
                selected[key]=(when,p,m['official_winner'])
        except (ValueError,TypeError,KeyError,OverflowError):
            invalid+=1
    scores={}
    for (slug,model),(_,p,winner) in selected.items():
        score=scores.setdefault(model,dict(markets=0,correct=0,brier_sum=0.,log_loss_sum=0.))
        actual=int(winner=='UP')
        score['markets']+=1
        score['correct']+=int((p>=.5)==bool(actual))
        score['brier_sum']+=(p-actual)**2
        bounded=max(.000001,min(.999999,p))
        score['log_loss_sum']-=actual*math.log(bounded)+(1-actual)*math.log(1-bounded)
    for score in scores.values():
        score['accuracy']=score['correct']/score['markets']
        score['brier']=score.pop('brier_sum')/score['markets']
        score['log_loss']=score.pop('log_loss_sum')/score['markets']
    return dict(status='CONNECTED',asset=asset,duration_seconds=seconds,verified_markets=len(outcomes),
                models=scores,invalid_predictions=invalid)


def load_history(get,asset,duration):
    """Bounded recent cohort, with one first-valid observation per model/market."""
    seconds={'5m':300,'15m':900}[duration]
    markets=get('asset_market_windows',dict(select='market_slug,asset,duration_seconds,window_start,window_end,settlement_status,official_winner,settlement_evidence',
        asset='eq.'+asset,duration_seconds='eq.'+str(seconds),settlement_status='eq.VERIFIED',order='window_end.desc,market_slug.asc',limit='20'))
    if not isinstance(markets,list):
        raise ValueError('Unexpected cloud market response')
    predictions=[]
    # Fetch one bounded cohort together; avoid a request per market on every
    # page render. Pagination still includes every prediction in the cohort.
    import re
    slugs=[m['market_slug'] for m in markets if m.get('asset')==asset and m.get('duration_seconds')==seconds]
    if any(not re.fullmatch(r'[a-z0-9-]{1,180}',slug) for slug in slugs):
        raise ValueError('Unexpected market identity')
    offset=0
    while slugs:
        rows=get('asset_market_predictions',dict(select='market_slug,recorded_at,model_version,predicted_up_probability,source_timestamp',
            market_slug='in.('+','.join(slugs)+')',order='recorded_at.asc,model_version.asc,market_slug.asc',limit='1000',offset=str(offset)))
        if not isinstance(rows,list):
            raise ValueError('Unexpected cloud prediction response')
        predictions.extend(rows)
        if len(rows)<1000:
            break
        offset+=1000
        if offset>=10000:
            raise ValueError('History pagination bound reached; refusing partial accuracy')
    result=summarize(markets,predictions,asset,seconds)
    result['cohort']='Most recent up to 20 verified markets; first valid prediction per model/market'
    return result
