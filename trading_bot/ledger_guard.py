"""Reject foreign or differently configured ledgers before any schema writes."""
from pathlib import Path
import sqlite3


def check_existing(path,expected_settings):
    if str(path)==':memory:': return
    path=Path(path)
    if not path.exists() or path.stat().st_size==0: return
    try:
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            row=db.execute('SELECT payload FROM settings WHERE id=1').fetchone()
    except sqlite3.Error as exc:
        raise ValueError('Not a recognized paper ledger; choose a separate database') from exc
    if not row or row[0]!=expected_settings:
        raise ValueError('Foreign or differently configured ledger; no schema changes made')
