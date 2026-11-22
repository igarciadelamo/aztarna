"""SQLite storage living next to the backend (DATA_DIR volume in Docker).

Privacy rule: never store user coordinates, IPs or anything per-request here (PRODUCT.md §3).
"""

import os
import sqlite3
from pathlib import Path

SCHEMA = """
-- Add tables here; statements must be idempotent (CREATE ... IF NOT EXISTS).
"""


def path() -> Path:
    return Path(os.environ.get("DATA_DIR", "data")) / "aztarna.db"


def connect() -> sqlite3.Connection:
    db_path = path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
