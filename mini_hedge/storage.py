"""SQLite persistence layer — stores and retrieves economic observations."""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Running this file directly (e.g. PyCharm) sets sys.path[0] to mini_hedge/, so
# `import mini_hedge` can fail or resolve a different tree. Put repo root on path first.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from mini_hedge.config import DB_PATH
except ImportError:
    # Older/divergent config.py without DB_PATH — match config layout.
    DB_PATH = _REPO_ROOT / "data" / "econ.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS observations (
    series_id   TEXT NOT NULL,
    date        TEXT NOT NULL,
    value       REAL NOT NULL,
    source      TEXT NOT NULL,
    footnotes   TEXT DEFAULT '',
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (series_id, date)
);
"""

_CREATE_VOL_INDICES = """
CREATE TABLE IF NOT EXISTS vol_indices (
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,
    close       REAL NOT NULL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);
"""

def get_connection(db_path=None):
    """Return a connection to the SQLite database, creating the data/ dir if needed."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    init_db(conn)
    return conn


def init_db(conn):
    """Create core tables if they don't exist (observations + Path 3 vol_indices)."""
    conn.execute(_CREATE_TABLE)
    conn.execute(_CREATE_VOL_INDICES)
    conn.commit()


def upsert_observations(df, source, conn=None):
    """Insert or replace observations. Returns count of rows upserted.

    Expects a DataFrame with columns: series_id, date, value
    Optional column: footnotes
    """
    should_close = conn is None
    if conn is None:
        conn = get_connection()

    now = datetime.utcnow().isoformat()
    rows = 0

    for _, row in df.iterrows():
        conn.execute(
            "INSERT OR REPLACE INTO observations "
            "(series_id, date, value, source, footnotes, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                row["series_id"],
                str(row["date"])[:10],   # YYYY-MM-DD
                float(row["value"]),
                source,
                row.get("footnotes", ""),
                now,
            ),
        )
        rows += 1

    conn.commit()
    if should_close:
        conn.close()
    return rows


def query_series(series_id, months=None, conn=None):
    """Read observations for a series from the DB as a DataFrame.

    If months is given, limit to the last N months.
    Returns DataFrame sorted by date descending.
    """
    should_close = conn is None
    if conn is None:
        conn = get_connection()

    if months:
        query = (
            "SELECT series_id, date, value, source, footnotes, fetched_at "
            "FROM observations WHERE series_id = ? "
            "ORDER BY date DESC LIMIT ?"
        )
        params = (series_id, months)
    else:
        query = (
            "SELECT series_id, date, value, source, footnotes, fetched_at "
            "FROM observations WHERE series_id = ? "
            "ORDER BY date DESC"
        )
        params = (series_id,)

    df = pd.read_sql_query(query, conn, params=params)

    if should_close:
        conn.close()
    return df


def upsert_vol_indices(df, conn=None):
    """Insert or replace rows in vol_indices. Idempotent re-runs.

    Expects columns: ticker, date, close  (date may be datetime or str YYYY-MM-DD)
    """
    should_close = conn is None
    if conn is None:
        conn = get_connection()

    now = datetime.utcnow().isoformat()
    rows = 0
    for _, row in df.iterrows():
        d = row["date"]
        if hasattr(d, "strftime"):
            d = d.strftime("%Y-%m-%d")
        else:
            d = str(d)[:10]
        conn.execute(
            "INSERT OR REPLACE INTO vol_indices (ticker, date, close, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            (str(row["ticker"]), d, float(row["close"]), now),
        )
        rows += 1
    conn.commit()
    if should_close:
        conn.close()
    return rows


def query_vol_index(ticker, days=None, last_n=None, conn=None):
    """Read vol index closes for one ticker from vol_indices.

    ``days`` — only rows with ``date`` on/after ``today - days`` (calendar).
    ``last_n`` — at most the last ``last_n`` rows by date (applied after ``days`` filter).
    Returns DataFrame sorted ascending by ``date``.
    """
    should_close = conn is None
    if conn is None:
        conn = get_connection()

    if days is not None:
        cutoff = (datetime.utcnow() - timedelta(days=int(days))).strftime("%Y-%m-%d")
        q = (
            "SELECT ticker, date, close, fetched_at FROM vol_indices "
            "WHERE ticker = ? AND date >= ? ORDER BY date ASC"
        )
        df = pd.read_sql_query(q, conn, params=(ticker, cutoff))
    else:
        q = (
            "SELECT ticker, date, close, fetched_at FROM vol_indices "
            "WHERE ticker = ? ORDER BY date ASC"
        )
        df = pd.read_sql_query(q, conn, params=(ticker,))

    if last_n is not None and not df.empty:
        df = df.tail(int(last_n)).reset_index(drop=True)

    if should_close:
        conn.close()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


if __name__ == "__main__":
    p = get_connection()
    p.close()
    print(f"OK — database initialized at {DB_PATH}")
