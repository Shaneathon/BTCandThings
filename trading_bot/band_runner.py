"""Paper-only market-band strategy runner; collector and live adapters unchanged."""
import argparse
import json
from pathlib import Path
import time
from trading_bot.market_band import BAND_SETTINGS
from trading_bot.observed_paper import Engine as BaseEngine,BookClient,cycle
from trading_bot.input_packet import read_packet

class Engine(BaseEngine):
    def __init__(self,path): super().__init__(path,settings=BAND_SETTINGS)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--kill-file',type=Path,required=True)
    args=parser.parse_args();engine=Engine(args.ledger);client=BookClient(engine)
    try:
        while True:
            try: data=read_packet(args.input)
            except (OSError,ValueError) as error:
                data=dict(input_error='INPUT_TOO_LARGE' if str(error)=='INPUT_TOO_LARGE' else 'INPUT_UNREADABLE_OR_INVALID')
            report=cycle(engine,data,client,time.time(),paused=args.kill_file.exists())
            print(json.dumps(dict(mode=report['operation_mode'],input=report['input_status'],live_orders=False)),flush=True)
            time.sleep(1)
    finally: engine.close()

if __name__=='__main__': main()
