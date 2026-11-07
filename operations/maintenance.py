"""Backup/health jobs. Never stop collectors, place orders or send messages."""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
from html import escape
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import uuid

STATE=Path('/var/lib/shaneathon-ops')
SERVICES=('btc-collector.service','btc-challenger.service','btc-multiasset-research.service',
          'coin-collector.service','coin-status.service','coin-dashboard.service',
          'pbot-sandbox-input.timer','pbot-paper.service','pbot-status.service','pbot-dashboard.service',
          'cbot-paper.service','cbot-status.service','cbot-dashboard.service','coinbase-recorder.service')


def stamp(): return datetime.now(timezone.utc).isoformat()


def atomic_json(path,data,group=None):
    path=Path(path)
    fd,temporary=tempfile.mkstemp(dir=path.parent,prefix='.status-')
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream,indent=2,allow_nan=False);stream.flush();os.fsync(stream.fileno())
        if group is not None: os.chown(temporary,0,group);os.chmod(temporary,0o640)
        os.replace(temporary,path)
    finally: Path(temporary).unlink(missing_ok=True)


def copy_database(source,destination,timeout=120):
    source,destination=Path(source),Path(destination)
    if source.is_symlink() or not source.is_file(): raise ValueError('Source must be a regular database, not a symlink')
    if source.resolve()==destination.resolve(): raise ValueError('Backup destination must be separate')
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    started=time.monotonic()
    def progress(status,remaining,total):
        if time.monotonic()-started>timeout: raise TimeoutError('Database backup deadline exceeded')
    try:
        with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=5) as original:
            target=sqlite3.connect(destination)
            try:
                original.backup(target,pages=128,progress=progress,sleep=.05)
                if target.execute('PRAGMA quick_check').fetchall()!=[('ok',)]: raise ValueError('Restored database failed integrity check')
            finally: target.close()
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def inventory():
    sources=[Path('/var/lib/btcandthings-research/research.sqlite'),Path('/var/lib/coin/research.sqlite')]
    sources.append(Path('/var/lib/btc-metals-proxy/quotes.sqlite'))
    for folder in ('/var/lib/pbot','/var/lib/cbot'):
        sources.extend(sorted(Path(folder).glob('*.sqlite')))
    sources.extend(Path('/root/BTCandThings/BTCandThings_Website/BTCandThings_Upload').glob('*.sqlite3'))
    return [p for p in sources if p.is_file() and not p.is_symlink()]


def prune(folder,max_sets=24,max_bytes=4*1024**3):
    # Only completed directories created by this tool are candidates. Never raw data.
    candidates=[]
    for path in Path(folder).glob('set-*'):
        if path.is_symlink() or not path.is_dir(): continue
        try: manifest=json.loads((path/'manifest.json').read_text())
        except (OSError,ValueError): continue
        if manifest.get('format')!='shaneathon-backup-v1' or manifest.get('complete') is not True: continue
        candidates.append((path,sum(p.stat().st_size for p in path.iterdir() if p.is_file()),manifest.get('completed_at',path.name)))
    candidates.sort(key=lambda row:row[2])
    while len(candidates)>2 and (len(candidates)>max_sets or sum(row[1] for row in candidates)>max_bytes):
        old,_,_=candidates.pop(0);shutil.rmtree(old)


def backup(folder,sources=None,minimum_free=4*1024**3):
    folder=Path(folder);folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    sources=inventory() if sources is None else list(sources)
    if not sources: raise ValueError('No databases found; refusing an empty successful backup')
    expected=sum(p.stat().st_size for p in sources)
    if shutil.disk_usage(folder).free<minimum_free+2*expected: raise ValueError('Insufficient disk headroom for consistent backup')
    temporary=Path(tempfile.mkdtemp(dir=folder,prefix='.incomplete-'))
    manifest=dict(format='shaneathon-backup-v1',complete=False,started_at=stamp(),databases=[],
                  consistency='Each SQLite database is individually consistent; not a cross-database transaction.',
                  excludes=['credentials','password hashes','TLS keys','raw-stream archives','remote Supabase rows'])
    try:
        for index,source in enumerate(sources):
            print('Snapshotting:',str(source),flush=True)
            copied=temporary/(str(index)+'-'+source.name)
            copy_database(source,copied)
            compressed=copied.with_name(copied.name+'.gz')
            with copied.open('rb') as reader,gzip.open(compressed,'wb',compresslevel=1) as writer:
                shutil.copyfileobj(reader,writer,1024**2)
            compressed.chmod(0o600);copied.unlink()
            digest=hashlib.sha256()
            with compressed.open('rb') as reader:
                for block in iter(lambda:reader.read(1024**2),b''): digest.update(block)
            manifest['databases'].append(dict(source=str(source),archive=compressed.name,sha256=digest.hexdigest(),
                                               compressed_bytes=compressed.stat().st_size,restore_quick_check='ok'))
        manifest.update(complete=True,completed_at=stamp())
        atomic_json(temporary/'manifest.json',manifest)
        target=folder/('set-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
        temporary.rename(target)
        atomic_json(folder.parent/'backup-status.json',dict(state='OK',completed_at=manifest['completed_at'],
                      database_count=len(sources),backup_set=str(target),credentials_included=False))
        prune(folder)
        print('Consistent local backup completed:',len(sources),'databases; restore integrity checked.')
        return manifest
    finally:
        if temporary.exists(): shutil.rmtree(temporary)


def cloud_export(folder,get=urlopen):
    folder=Path(folder);folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    base=os.environ.get('SUPABASE_URL','').strip().rstrip('/')
    key=os.environ.get('SUPABASE_KEY','').strip()
    if not base.startswith('https://') or not key: raise ValueError('Private Supabase read configuration unavailable')
    headers={'apikey':key}
    if not key.startswith('sb_secret_'): headers['Authorization']='Bearer '+key
    temporary=Path(tempfile.mkdtemp(dir=folder,prefix='.incomplete-'))
    manifest=dict(format='shaneathon-backup-v1',complete=False,started_at=stamp(),tables=[],
                  consistency='Paginated REST exports, not an atomic Supabase transaction or full schema backup.')
    tables=[('btc_markets','market_slug.asc'),('btc_predictions','recorded_at.asc,market_slug.asc,model_version.asc'),
            ('btc_challenger_predictions','recorded_at.asc,market_slug.asc,model_version.asc')]
    try:
        for table,order in tables:
            path=temporary/(table+'.jsonl.gz');count=0
            with gzip.open(path,'wt',compresslevel=1) as output:
                for page in range(10000):
                    params=dict(select='*',order=order,limit=1000,offset=count)
                    params['window_start' if table=='btc_markets' else 'recorded_at']='lte.'+manifest['started_at']
                    req=Request(base+'/rest/v1/'+table+'?'+urlencode(params),headers=headers,method='GET')
                    try:
                        with get(req,timeout=30) as response: rows=json.load(response)
                    except Exception as error:
                        raise RuntimeError(table+' export failed: '+type(error).__name__) from None
                    if not isinstance(rows,list): raise ValueError('Invalid export response')
                    if not rows: break
                    for row in rows: output.write(json.dumps(row,allow_nan=False)+'\n')
                    count+=len(rows)
                    time.sleep(.1)
                else: raise ValueError('Cloud pagination limit; refusing incomplete export')
            path.chmod(0o600)
            if count==0: raise ValueError('Expected nonempty production table; refusing empty cloud export')
            manifest['tables'].append(dict(table=table,rows=count,archive=path.name))
        manifest.update(complete=True,completed_at=stamp())
        atomic_json(temporary/'manifest.json',manifest)
        temporary.rename(folder/('set-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]))
        atomic_json(folder.parent/'cloud-status.json',dict(state='OK',completed_at=manifest['completed_at'],tables=manifest['tables']))
        prune(folder,max_sets=7,max_bytes=1024**3)
        print('Read-only cloud-data exports complete:',[(t['table'],t['rows']) for t in manifest['tables']])
    finally:
        if temporary.exists(): shutil.rmtree(temporary)


def age(value,now):
    if isinstance(value,(int,float)): return now-value
    return now-datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()


def health(folder,service_check=None,publish=True):
    folder=Path(folder);folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    now=time.time();issues=[];checks={}
    for name in SERVICES:
        if service_check:
            active=service_check(name)
        else:
            try: active=subprocess.run(['systemctl','is-active','--quiet',name],timeout=5).returncode==0
            except subprocess.TimeoutExpired: active=False
        checks[name]='active' if active else 'NOT_ACTIVE'
        if not active: issues.append(dict(level='critical',message=name+' is not active'))
    if Path('/etc/systemd/system/btc-metals-proxy.service').is_file():
        name='btc-metals-proxy.service'
        if service_check: active=service_check(name)
        else:
            try: active=subprocess.run(['systemctl','is-active','--quiet',name],timeout=5).returncode==0
            except subprocess.TimeoutExpired: active=False
        checks[name]='active' if active else 'NOT_ACTIVE'
        if not active: issues.append(dict(level='critical',message='Metals quote sampler is not active'))
    databases=[('/var/lib/btcandthings-research/research.sqlite','collector_status',240,'Research collector'),
               ('/var/lib/coin/research.sqlite','tracker_status',180,'Coinbase tracker'),
               ('/var/lib/pbot/comparison.sqlite','bot_snapshot',60,'Polymarket paper experiments'),
               ('/var/lib/cbot/paper.sqlite','bot_snapshot',180,'Coinbase paper bot')]
    freshness={}
    for source,table,limit,label in databases:
        try:
            with sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True,timeout=3) as db:
                row=db.execute('SELECT observed_at,payload FROM '+table+' LIMIT 1').fetchone()
            elapsed=age(row[0],now);data=json.loads(row[1])
            freshness[label]=round(elapsed,1)
            if not 0<=elapsed<=limit: issues.append(dict(level='critical',message=label+' status is stale or clock is ahead'))
            if data.get('real_trading') is True or data.get('orders_enabled') is True or data.get('account',{}).get('live_orders_enabled') is True:
                issues.append(dict(level='critical',message=label+' reports live orders enabled'))
            for portfolio in list(data.get('portfolios',{}).values())+list(data.get('market_portfolios',{}).values()):
                if portfolio.get('account',{}).get('live_orders_enabled') is True:
                    issues.append(dict(level='critical',message='A paper portfolio reports live orders enabled'))
            if data.get('cloud_sync',{}).get('errors',0)>0: issues.append(dict(level='warning',message='Research cloud upload errors reported'))
            if table=='collector_status':
                for stream,state in data.get('streams',{}).items():
                    if not state.get('collection_ready'): issues.append(dict(level='notice',message=stream+' prediction collection paused'))
        except (OSError,sqlite3.Error,TypeError,ValueError,IndexError):
            issues.append(dict(level='critical',message=label+' status could not be read'))
    try:
        recorder=json.loads(Path('/var/lib/coinbase-recorder/status.json').read_text())
        if age(recorder['updated_at'],now)>90 or recorder.get('state')!='CAPTURING_RAW':
            issues.append(dict(level='warning',message='Raw Coinbase capture is stale, disconnected or budget-paused'))
        if recorder.get('real_trading') is True: issues.append(dict(level='critical',message='Recorder unexpectedly reports real trading'))
    except (OSError,ValueError,KeyError): issues.append(dict(level='warning',message='Raw recorder status unavailable'))
    backups={}
    for filename,limit,label in [('backup-status.json',3*3600,'Local database snapshots'),('cloud-status.json',36*3600,'Cloud data export')]:
        try:
            status=json.loads((folder/filename).read_text());backups[label]=status
            if age(status['completed_at'],now)>limit or status['state']!='OK': raise ValueError('Stale backup')
        except (OSError,ValueError,KeyError): issues.append(dict(level='warning',message=label+' has no recent successful run'))
    for job in ('backup','cloud'):
        if (folder/(job+'-failure.json')).is_file():
            issues.append(dict(level='warning',message='The most recent '+job+' job failed; prior completed sets are preserved'))
    free=shutil.disk_usage('/').free
    if free<4*1024**3: issues.append(dict(level='critical',message='Root disk has less than 4 GiB available'))
    memory_available=None
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'): memory_available=int(line.split()[1])*1024
        if memory_available is not None and memory_available<256*1024**2:
            issues.append(dict(level='warning',message='Available memory is below 256 MiB'))
    except (OSError,ValueError): pass
    report=dict(checked_at=stamp(),state='CRITICAL' if any(i['level']=='critical' for i in issues) else 'WARNING' if any(i['level']=='warning' for i in issues) else 'OK',
                services=checks,status_age_seconds=freshness,issues=issues,backups=backups,root_free_gib=round(free/1024**3,2),
                memory_available_mib=round(memory_available/1024**2) if memory_available is not None else None,
                external_notifications_configured=False,provider_backups='Daily enabled by user; first completion not verified by this job.')
    atomic_json(folder/'health.json',report)
    portal=Path('/var/www/shaneathon-portal')
    if publish and portal.is_dir() and not portal.is_symlink():
        content=('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Shaneathon health</title><link rel="stylesheet" href="/portal.css"></head><body><main><p class="eyebrow">SHANEATHON</p><h1>System health: '''+escape(report['state'])+'</h1><p class="intro">Checked '+escape(report['checked_at'])+'</p><section class="card"><h2>Checks</h2><ul>'+''.join('<li>'+escape(item['level']+': '+item['message'])+'</li>' for item in issues)+'</ul><p>'+str(len(checks))+' services checked. '+str(report['root_free_gib'])+' GiB disk available.</p><p>Alerts are recorded here and in the server journal; external notifications are not configured.</p></section><p><a href="/">Back to portal</a></p></main></body></html>')
        fd,temporary=tempfile.mkstemp(dir=portal,prefix='.health-')
        try:
            with os.fdopen(fd,'w') as stream: stream.write(content)
            os.chown(temporary,0,portal.stat().st_gid);os.chmod(temporary,0o640)
            os.replace(temporary,portal/'health.html')
        finally: Path(temporary).unlink(missing_ok=True)
    print('Health:',report['state'],'| alerts:',len([i for i in issues if i['level']!='notice']))
    for item in issues: print(item['level'].upper()+': '+item['message'])
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job',choices=('backup','cloud','health'))
    parser.add_argument('--state',type=Path,default=STATE)
    args=parser.parse_args();os.umask(0o077)
    try:
        if args.job=='backup': backup(args.state/'sqlite')
        elif args.job=='cloud': cloud_export(args.state/'cloud')
        else:
            report=health(args.state)
            if report['state']=='CRITICAL': raise SystemExit(1)
        (args.state/(args.job+'-failure.json')).unlink(missing_ok=True)
    except Exception as error:
        args.state.mkdir(mode=0o700,parents=True,exist_ok=True)
        atomic_json(args.state/(args.job+'-failure.json'),dict(failed_at=stamp(),job=args.job,error=type(error).__name__))
        print('Maintenance job failed:',args.job,type(error).__name__,'(no credentials displayed)')
        raise SystemExit(1)
