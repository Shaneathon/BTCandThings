"""Bounded public-channel diagnostic. No keys, accounts, orders or file writes."""
import asyncio
import json
import time
from market_capture.coinbase_ws import URL,PRODUCTS


async def probe(channel):
    from websockets.asyncio.client import connect
    result=dict(channel=channel,messages=0,received_channels={},state='NO_DATA')
    try:
        async with connect(URL,open_timeout=10,max_size=4*1024**2,ping_interval=20) as socket:
            message=dict(type='subscribe',channel=channel)
            if channel!='heartbeats': message['product_ids']=PRODUCTS
            await socket.send(json.dumps(message))
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                try: wire=await asyncio.wait_for(socket.recv(),timeout=max(.1,deadline-time.monotonic()))
                except asyncio.TimeoutError: break
                data=json.loads(wire)
                result['messages']+=1
                received=data.get('channel',data.get('type','UNKNOWN'))
                result['received_channels'][received]=result['received_channels'].get(received,0)+1
                if data.get('type')=='error':
                    result.update(state='REJECTED',message=str(data.get('message',''))[:300]);break
                if data.get('events'): result['state']='DATA_RECEIVED'
    except Exception as error:
        result.update(state='ERROR',error=type(error).__name__)
        frame=getattr(error,'rcvd',None)
        if frame is not None: result.update(close_code=frame.code,close_reason=frame.reason)
        elif getattr(error,'code',None) is not None: result['close_code']=error.code
    return result


async def main():
    for result in await asyncio.gather(*(probe(channel) for channel in ('heartbeats','market_trades','level2'))):
        print(json.dumps(result),flush=True)


if __name__=='__main__': asyncio.run(main())
