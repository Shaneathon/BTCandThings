#!/usr/bin/env python3
"""Read-only audit of production BTC Champion/Challengers; no model changes."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from research_report import utc, wilson


def fetch(table, columns, order, cutoff, get=urlopen):
    key = os.environ['SUPABASE_KEY'].strip()
    base = os.environ['SUPABASE_URL'].strip().rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('HTTPS Supabase URL required')
    headers = {'apikey': key, 'Accept': 'application/json'}
    if not key.startswith('sb_secret_'):
        headers['Authorization'] = 'Bearer ' + key
    result = []
    # Freeze the observation cutoff so new predictions cannot shift pagination.
    for page in range(2000):
        query = dict(select=columns, order=order, limit=1000, offset=page*1000)
        query['recorded_at' if 'predictions' in table else 'window_end'] = 'lte.'+cutoff
        request = Request(base+'/rest/v1/'+table+'?'+urlencode(query), headers=headers, method='GET')
        try:
            with get(request, timeout=30) as response:
                rows = json.load(response)
        except Exception as error:
            raise RuntimeError(table+' read failed: '+type(error).__name__+
                               ' HTTP '+str(getattr(error, 'code', 'unknown'))) from None
        if not isinstance(rows, list):
            raise ValueError('Unexpected table response')
        result.extend(rows)
        if not rows:
            return result
        # Do not assume the server's row cap is 1000.
        if len(rows) < 1000:
            # Advance by actual rows on the next call via a separate offset.
            return fetch_remaining(table, query, headers, base, result, get)
        time.sleep(.05)
    raise RuntimeError('Pagination limit reached; refusing incomplete audit')


def fetch_remaining(table, query, headers, base, result, get):
    for _ in range(20000):
        query['offset'] = len(result)
        request = Request(base+'/rest/v1/'+table+'?'+urlencode(query), headers=headers, method='GET')
        try:
            with get(request, timeout=30) as response:
                rows = json.load(response)
        except Exception as error:
            raise RuntimeError(table+' pagination failed: '+type(error).__name__) from None
        if not isinstance(rows, list):
            raise ValueError('Unexpected table response')
        if not rows:
            return result
        result.extend(rows)
        time.sleep(.05)
    raise RuntimeError('Pagination limit reached')


def stats(rows):
    n = len(rows)
    if not n:
        return {'markets': 0}
    wins = sum((p >= .5) == bool(y) for _, p, y in rows)
    bins = []
    for index in range(5):
        lo = index/5
        group = [(p,y) for _,p,y in rows if min(4,int(p*5)) == index]
        if group:
            bins.append(dict(range=f'{lo:.1f}-{lo+.2:.1f}', markets=len(group),
                             mean_probability=round(sum(p for p,_ in group)/len(group),4),
                             actual_up=round(sum(y for _,y in group)/len(group),4)))
    return dict(markets=n, accuracy=round(wins/n,4), accuracy_95_interval=wilson(wins,n),
                brier=round(sum((p-y)**2 for _,p,y in rows)/n,6),
                log_loss=round(-sum(y*math.log(max(1e-12,p))+(1-y)*math.log(max(1e-12,1-p))
                                    for _,p,y in rows)/n,6),
                always_up_accuracy=round(sum(y for _,_,y in rows)/n,4),
                coin_flip_brier=.25, calibration=bins)


def review(markets, sources, duration=900):
    verified = {}
    for m in markets:
        start, end = utc(m.get('window_start')), utc(m.get('window_end'))
        if (m.get('settlement_status') == 'VERIFIED' and m.get('official_winner') in ('UP','DOWN')
                and start and end and (end-start).total_seconds() == duration
                and str(m.get('market_slug','')).startswith(f'btc-updown-{duration//60}m-')):
            verified[m['market_slug']] = (start.timestamp(),end.timestamp(),int(m['official_winner']=='UP'))
    models = defaultdict(list)
    rejected = Counter()
    totals = {}
    for source, records in sources.items():
        totals[source] = len(records)
        for row in records:
            model = source+': '+str(row.get('model_version') or 'UNVERSIONED')
            try:
                when = utc(row.get('recorded_at'))
                probability = float(row['predicted_up_probability'])
                window = verified.get(row['market_slug'])
                if not window:
                    rejected['not_verified_btc_15m'] += 1
                    continue
                if not when or not math.isfinite(probability) or not 0 <= probability <= 1:
                    raise ValueError()
                stamp = when.timestamp()
                if not window[0] <= stamp < window[1]:
                    rejected['outside_market_window'] += 1
                    continue
                models[model].append((row['market_slug'], stamp, probability))
            except (KeyError,TypeError,ValueError,OverflowError):
                rejected['invalid_prediction'] += 1
    report = dict(verified_btc_markets=len(verified), duration_seconds=duration, source_rows=totals,
                  excluded_rows=dict(rejected), models=sorted(models), horizons={})
    for horizon in (600,300,180,60):
        if horizon >= duration:
            continue
        selected = {}
        for model, predictions in models.items():
            chosen = {}
            for slug, stamp, p in predictions:
                checkpoint = verified[slug][1]-horizon
                # Only observations known by the checkpoint; never pick a later prediction.
                if 0 <= checkpoint-stamp <= 90:
                    prior = chosen.get(slug)
                    if prior is None or stamp > prior[0]:
                        chosen[slug] = (stamp,p)
            selected[model] = chosen
        common = set.intersection(*(set(v) for v in selected.values())) if selected else set()
        def scored(chosen, cohort):
            return sorted([(verified[s][1],chosen[s][1],verified[s][2]) for s in cohort])
        entry = dict(common_markets=len(common), models={}, pairwise=[])
        for model, chosen in selected.items():
            paired = scored(chosen, common)
            split = len(paired)//2
            entry['models'][model] = dict(own_coverage=stats(scored(chosen,set(chosen))),
                                          paired=stats(paired), later_half=stats(paired[split:]))
        for champion, champion_rows in selected.items():
            if not champion.startswith('Champion: '):
                continue
            for challenger, challenger_rows in selected.items():
                if not challenger.startswith('Challenger: '):
                    continue
                shared = sorted(set(champion_rows) & set(challenger_rows), key=lambda s:(verified[s][1],s))
                if not shared:
                    continue
                pair = dict(champion=champion, challenger=challenger, markets=len(shared))
                for label, subset in [('all', shared), ('later_half', shared[len(shared)//2:])]:
                    c, d = stats(scored(champion_rows, subset)), stats(scored(challenger_rows, subset))
                    pair[label] = dict(champion=c, challenger=d,
                                       challenger_minus_champion_brier=round(d['brier']-c['brier'],6))
                entry['pairwise'].append(pair)
        report['horizons'][str(horizon)] = entry
    report['limits'] = ['Only verified BTC outcomes matching this duration; different sources are scored separately.',
        'One observation per market/model/checkpoint, at most 90 seconds old.',
        'Common cohort requires every observed model version; version changes may make it small or empty.',
        'Later half is descriptive temporal validation, not an untouched holdout after reviewing this report.',
        'Accuracy intervals assume independent markets; adjacent windows may be correlated.',
        'No trading profitability or strategy promotion is inferred.']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--research-db',type=Path)
    parser.add_argument('--compact',action='store_true')
    args = parser.parse_args()
    cutoff = datetime.now(timezone.utc).isoformat()
    markets = fetch('btc_markets','market_slug,window_start,window_end,settlement_status,official_winner',
                    'window_start.asc,market_slug.asc',cutoff)
    sources = {}
    for name, table in [('Champion','btc_predictions'),('Challenger','btc_challenger_predictions')]:
        sources[name] = fetch(table,'market_slug,recorded_at,predicted_up_probability,model_version',
                              'recorded_at.asc,market_slug.asc,model_version.asc',cutoff)
    report = review(markets,sources)
    report['cutoff_utc'] = cutoff
    if args.research_db:
        import sqlite3
        with sqlite3.connect(args.research_db.resolve().as_uri()+'?mode=ro',uri=True) as db:
            local_markets=[json.loads(r[0]) for r in db.execute("SELECT payload FROM records WHERE kind='market'")]
            local_predictions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM research_snapshots')]
        report['separate_btc_research'] = {
            str(duration): review(local_markets,{'Research baseline':local_predictions},duration)
            for duration in (300,900)}
    fd = os.open(args.out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print('BTC REVIEW — '+cutoff)
    print('Verified BTC 15m markets:',report['verified_btc_markets'])
    print('Fetched prediction rows:',json.dumps(report['source_rows']))
    print('Excluded rows:',json.dumps(report['excluded_rows']))
    for horizon,entry in report['horizons'].items():
        print('\nHORIZON',horizon,'seconds | common markets:',entry['common_markets'])
        for model,result in entry['models'].items():
            if args.compact:
                data=result['own_coverage']
                print(model,json.dumps({k:v for k,v in data.items() if k in ('markets','accuracy','brier','log_loss')}))
                continue
            print(model)
            for cohort in ('own_coverage','paired','later_half'):
                data=result[cohort]
                print(' ',cohort,json.dumps({k:v for k,v in data.items() if k!='calibration'}))
            print('  own_coverage calibration:',json.dumps(result['own_coverage'].get('calibration',[])))
        for pair in entry['pairwise']:
            print('PAIRED:',pair['champion'],'vs',pair['challenger'])
            for label in ('all','later_half'):
                cohort=pair[label]
                print(' ',label,json.dumps(dict(markets=cohort['champion']['markets'],
                      champion_accuracy=cohort['champion']['accuracy'],
                      challenger_accuracy=cohort['challenger']['accuracy'],
                      champion_brier=cohort['champion']['brier'],
                      challenger_brier=cohort['challenger']['brier'],
                      challenger_minus_champion_brier=cohort['challenger_minus_champion_brier'])))
    print('\nLIMITS:',json.dumps(report['limits']))
    for duration,local in report.get('separate_btc_research',{}).items():
        print('\nSEPARATE BTC RESEARCH:',duration,'seconds | verified markets:',local['verified_btc_markets'])
        for horizon,entry in local['horizons'].items():
            for model,result in entry['models'].items():
                print(' ',horizon,model,json.dumps({k:v for k,v in result['own_coverage'].items() if k!='calibration'}))
    print('Full report saved privately:',str(args.out))


if __name__ == '__main__':
    main()
