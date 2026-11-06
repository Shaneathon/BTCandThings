"""Consistent, exclusive SQLite seeding. Never overwrites an existing database."""
import argparse
import os
from pathlib import Path
import sqlite3


def seed(source,destination):
    source,destination=Path(source),Path(destination)
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as original:
        names={row[0] for row in original.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'records','research_snapshots','collector_status'}<=names:
            raise ValueError('Source is not a multiasset research database')
        fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        os.close(fd)
        try:
            with sqlite3.connect(destination) as copy:
                original.backup(copy)
        except Exception:
            destination.unlink()
            raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    seed(args.source,args.destination)
    print('Existing research observations copied consistently; source database unchanged.')


if __name__=='__main__': main()
