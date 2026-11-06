"""Render only an immutable release-path update for the research collector."""
import argparse
from pathlib import Path
import re


def render(text,old,new):
    pattern=r'/opt/btcandthings-research/releases/[A-Za-z0-9_-]+'
    if not re.fullmatch(pattern,old) or not re.fullmatch(pattern,new) or old==new:
        raise ValueError('Expected distinct managed research release paths')
    if f'WorkingDirectory={old}\n' not in text or f'ExecStart={old}/venv/bin/python {old}/collection/ten_streams.py ' not in text:
        raise ValueError('Research unit does not match the expected layout')
    return text.replace(old,new)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit',type=Path,required=True)
    parser.add_argument('--old',required=True)
    parser.add_argument('--new',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    args.out.write_text(render(args.unit.read_text(),args.old,args.new))


if __name__=='__main__': main()
