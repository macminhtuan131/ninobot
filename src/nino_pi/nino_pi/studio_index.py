"""Local session index derived from fetched manifests, never a source of raw truth."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def database():
    return Path.home()/'.local/share/nino/studio_sessions.sqlite3'


def register(root,report,path=None):
    root=Path(root).resolve();meta=json.loads((root/'session.json').read_text())
    target=Path(path or database());target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(target) as db:
        db.execute('CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY,path TEXT,scenario TEXT,kind TEXT,quality TEXT,level TEXT,indexed_utc TEXT)')
        db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET path=excluded.path,quality=excluded.quality,level=excluded.level,indexed_utc=excluded.indexed_utc',
            (meta['session_id'],str(root),meta['scenario'],meta['dataset_kind'],report['verdict'],report['level'],datetime.now(timezone.utc).isoformat()))


def sessions(path=None):
    target=Path(path or database())
    if not target.exists():return []
    with sqlite3.connect(target.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        return [dict(r) for r in db.execute('SELECT * FROM sessions ORDER BY indexed_utc DESC LIMIT 200')]
