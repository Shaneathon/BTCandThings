"""Consistent exclusive backup of a Coinbase research DB; no foreign data."""
import argparse
import os
from pathlib import Path
import sqlite3
from coinbase_tracker.collector import APP_ID


def seed(source,destination):
    with sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True) as original:
        if original.execute('PRAGMA application_id').fetchone()[0]!=APP_ID:
            raise ValueError('Source is not a Coinbase research database')
        fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        os.close(fd)
        try:
            copy=sqlite3.connect(destination)
            try: original.backup(copy)
            finally: copy.close()
        except Exception:
            Path(destination).unlink()
            raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    seed(args.source,args.destination)
    print('Coinbase observations copied consistently; source unchanged.')
