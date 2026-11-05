"""Non-secret host-capacity inspection; no services or databases modified."""
import argparse
import json
from pathlib import Path
import shutil
import sys


def inspect(path, minimum_disk=1024**3, minimum_memory=256*1024**2):
    available=shutil.disk_usage(path).free
    memory=None
    info=Path('/proc/meminfo')
    if info.exists():
        for line in info.read_text().splitlines():
            if line.startswith('MemAvailable:'):
                memory=int(line.split()[1])*1024
    return dict(python_ok=sys.version_info>=(3,10),available_disk_bytes=available,
                available_memory_bytes=memory,disk_ok=available>=minimum_disk,
                memory_ok=memory is None or memory>=minimum_memory)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path',type=Path)
    args=parser.parse_args()
    report=inspect(args.path)
    print(json.dumps(report))
    raise SystemExit(0 if all(report[k] for k in ('python_ok','disk_ok','memory_ok')) else 1)


if __name__=='__main__':
    main()
