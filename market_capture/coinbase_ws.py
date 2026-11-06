"""Archive unauthenticated Coinbase messages for later replay, not trading.

No book reconstruction or fill assertions. Gaps/reconnects are explicit;
existing REST collectors and bots remain independent.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import random
import shutil
import tempfile
import time
import uuid

URL='wss://advanced-trade-ws.coinbase.com'
PRODUCTS=['BTC-USD','ETH-USD','XRP-USD','SOL-USD']


class CapturePaused(ValueError): pass


class Archive:
    def __init__(self,folder,daily_limit=512*1024**2,minimum_free=2*1024**3):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.daily_limit=daily_limit;self.minimum_free=minimum_free
        self.stream=None;self.path=None;self.segment_day=None;self.segment_bytes=0
        self.checked_at=0;self.daily_bytes=0
        self.last_lifecycle=None
        self.status=dict(mode='PUBLIC_DATA_CAPTURE',real_trading=False,book_ready=False,
                         note='Raw messages only; continuity and book reconstruction not validated.',
                         state='STARTING',session_messages=0,channels={},reconnects=0)

    def save_status(self):
        self.status['updated_at']=datetime.now(timezone.utc).isoformat()
        lifecycle=(self.status['state'],self.status.get('connection_id'))
        if lifecycle!=self.last_lifecycle:
            fd=os.open(self.folder/'lifecycle.jsonl',os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
            with os.fdopen(fd,'a') as log:
                log.write(json.dumps({k:self.status.get(k) for k in ('updated_at','state','connection_id','error','gap_opened_at')})+'\n')
            self.last_lifecycle=lifecycle
        fd,temporary=tempfile.mkstemp(dir=self.folder,prefix='.status-')
        try:
            with os.fdopen(fd,'w') as output: json.dump(self.status,output,allow_nan=False)
            os.replace(temporary,self.folder/'status.json')
        finally: Path(temporary).unlink(missing_ok=True)

    def check_budget(self,now):
        day=datetime.fromtimestamp(now,timezone.utc).strftime('%Y%m%d')
        if self.segment_day!=day or now-self.checked_at>=10:
            if self.stream: self.stream.flush()
            self.daily_bytes=sum(p.stat().st_size for p in self.folder.glob(day+'-*.jsonl.gz'))
            self.checked_at=now
            if shutil.disk_usage(self.folder).free<self.minimum_free:
                raise CapturePaused('LOW_DISK_CAPTURE_PAUSED')
            if self.daily_bytes>=self.daily_limit:
                raise CapturePaused('DAILY_ARCHIVE_BUDGET_REACHED')
        return day

    def write(self,wire,connection_id,now=None):
        now=time.time() if now is None else now
        day=self.check_budget(now)
        if not self.stream or self.segment_day!=day or self.segment_bytes>=16*1024**2:
            self.close_segment()
            self.segment_day=day;self.segment_bytes=0
            self.path=self.folder/(day+'-'+uuid.uuid4().hex+'.jsonl.gz')
            fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            self.stream=gzip.GzipFile(fileobj=os.fdopen(fd,'wb'),mode='wb')
        payload=json.loads(wire)
        if not isinstance(payload,dict): raise ValueError('Invalid public message envelope')
        line=json.dumps(dict(received_at=datetime.fromtimestamp(now,timezone.utc).isoformat(),
                             monotonic_ns=time.monotonic_ns(),connection_id=connection_id,
                             wire_json=wire),ensure_ascii=False,allow_nan=False).encode()+b'\n'
        self.stream.write(line);self.segment_bytes+=len(line)
        self.status['session_messages']+=1
        channel=str(payload.get('channel',payload.get('type','UNKNOWN')))
        self.status['channels'][channel]=self.status['channels'].get(channel,0)+1
        self.status['last_message_at']=datetime.fromtimestamp(now,timezone.utc).isoformat()
        self.status['archive_bytes_today']=self.daily_bytes
        return payload

    def close_segment(self):
        if self.stream:
            underlying=self.stream.fileobj
            self.stream.close()
            underlying.close()
            self.stream=None


async def collect(folder):
    from websockets.asyncio.client import connect
    archive=Archive(folder)
    failures=0
    try:
        while True:
            try:
                archive.check_budget(time.time())
                connection_id=uuid.uuid4().hex
                archive.status.update(state='CONNECTING',connection_id=connection_id)
                archive.save_status()
                async with connect(URL,open_timeout=15,ping_interval=20,ping_timeout=20,
                                   max_size=4*1024**2,max_queue=8) as socket:
                    connected_at=time.time()
                    for channel in ('heartbeats','market_trades','level2'):
                        await socket.send(json.dumps(dict(type='subscribe',channel=channel,product_ids=PRODUCTS)))
                    last_status=0
                    while True:
                        wire=await asyncio.wait_for(socket.recv(),timeout=45)
                        if isinstance(wire,bytes): wire=wire.decode('utf-8')
                        payload=archive.write(wire,connection_id)
                        if payload.get('type')=='error':
                            archive.status['subscription_error']=str(payload.get('message','Public channel rejected'))[:300]
                            raise ValueError('PUBLIC_SUBSCRIPTION_REJECTED')
                        now=time.time()
                        archive.status['state']='CAPTURING_RAW'
                        if now-last_status>=10:
                            archive.stream.flush();archive.save_status();last_status=now
                        # Reset backoff only after actual data has arrived.
                        if payload.get('events') and now-connected_at>=60: failures=0
            except CapturePaused as error:
                archive.close_segment()
                archive.status.update(state=str(error),gap_opened_at=datetime.now(timezone.utc).isoformat())
                archive.save_status()
                await asyncio.sleep(60)
            except Exception as error:
                archive.close_segment()
                failures=min(failures+1,8)
                archive.status.update(state='DISCONNECTED_OR_CHANNEL_UNAVAILABLE',error=type(error).__name__,
                    reconnects=archive.status['reconnects']+1,gap_opened_at=datetime.now(timezone.utc).isoformat())
                frame=getattr(error,'rcvd',None)
                if frame is not None:
                    archive.status.update(close_code=frame.code,close_reason=frame.reason)
                archive.save_status()
                await asyncio.sleep(min(300,2**failures)+random.random())
    finally:
        archive.close_segment()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    args=parser.parse_args()
    asyncio.run(collect(args.state))
