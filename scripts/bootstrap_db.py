#!/usr/bin/env python3
"""
bootstrap_db.py — One-time database population script.

Run this ONCE on your local machine to fill the SQLite database
before using transforms.py, surprises.py, or any notebook.

Usage:
    cd Mini_Hedge
    python3 scripts/bootstrap_db.py

What it fetches:
    FRED series  — full history via FRED API (free key required)
    BLS series   — full history via BLS API (free key required, optional)

After this runs, every other module reads from local SQLite and
never hits the API again unless you call fetch_* explicitly.

API keys go in .env at the project root:
    FRED_API_KEY=your_key_here
    BLS_API_KEY=your_key_here   (optional — only needed for BLS series)

Get a free FRED key: https://fred.stlouisfed.org/docs/api/api_key.html
Get a free BLS key:  https://data.bls.gov/registrationEngine/
"""

import sys
import time
from pathlib import Path

# Make sure imports resolve from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mini_hedge import config
from mini_hedge.fetchers import fetch_fred, fetch_bls, fetch_vol_index
from mini_hedge.storage import query_series

# ── Series to fetch ───────────────────────────────────────────────────────────

FRED_SERIES = {
    "CPILFESL": "Core CPI (seasonally adjusted)",
    "FEDFUNDS": "Federal Funds Rate (effective)",
    "DGS10":    "10-Year Treasury Yield (daily)",
    "CPIAUCSL": "CPI All Urban (seasonally adjusted)",
    "UNRATE":   "Unemployment Rate",
    "T10Y2Y":   "10Y-2Y Treasury Spread (recession proxy)",
    "PAYEMS":   "All Employees Total Nonfarm (NFP level, monthly)",
    "DFEDTARU": "Fed Funds Target Range — Upper (FOMC scaffold)",
}

BLS_SERIES = {
    "CUUR0000SA0": "CPI-U All Urban (not seasonally adjusted) — raw headline CPI",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(series_id: str, min_rows: int = 10) -> bool:
    """Return True if series already has data in the database."""
    try:
        df = query_series(series_id)
        return len(df) >= min_rows
    except Exception:
        return False


def _fetch_with_retry(fn, series_id: str, label: str, retries: int = 2):
    for attempt in range(1, retries + 2):
        try:
            df = fn(series_id)
            print(f"  ✓  {series_id:16s}  {label}  ({len(df):,} rows)")
            return df
        except Exception as e:
            if attempt <= retries:
                print(f"  ⚠  {series_id} — attempt {attempt} failed: {e}. Retrying...")
                time.sleep(2)
            else:
                print(f"  ✗  {series_id} — FAILED after {retries+1} attempts: {e}")
                return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main(force: bool = False):
    print("=" * 60)
    print("  Mini Hedge — Database Bootstrap")
    print(f"  DB path: {config.DB_PATH}")
    print("=" * 60)

    # Check API keys
    if not config.FRED_API_KEY:
        print("\n  ERROR: FRED_API_KEY not set.")
        print("  Add it to your .env file at the project root:")
        print("    FRED_API_KEY=your_key_here")
        print("  Get a free key: https://fred.stlouisfed.org/docs/api/api_key.html")
        sys.exit(1)

    has_bls_key = bool(config.BLS_API_KEY)
    if not has_bls_key:
        print("\n  NOTE: BLS_API_KEY not set — will skip BLS series.")
        print("        Get a free key: https://data.bls.gov/registrationEngine/")
        print("        Add BLS_API_KEY=your_key to .env, then re-run.")

    # Create data directory if needed
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ── FRED series ──
    print("\n── FRED Series ─────────────────────────────────────────────")
    fred_ok = 0
    for series_id, label in FRED_SERIES.items():
        if not force and _ok(series_id):
            df = query_series(series_id)
            print(f"  ↩  {series_id:16s}  already in DB ({len(df):,} rows) — skipping")
            fred_ok += 1
            continue
        result = _fetch_with_retry(fetch_fred, series_id, label)
        if result is not None:
            fred_ok += 1
        time.sleep(0.4)   # be polite to FRED

    # ── BLS series ──
    print("\n── BLS Series ──────────────────────────────────────────────")
    bls_ok = 0
    if has_bls_key:
        for series_id, label in BLS_SERIES.items():
            if not force and _ok(series_id):
                df = query_series(series_id)
                print(f"  ↩  {series_id:16s}  already in DB ({len(df):,} rows) — skipping")
                bls_ok += 1
                continue
            result = _fetch_with_retry(fetch_bls, series_id, label)
            if result is not None:
                bls_ok += 1
    else:
        print("  (skipped — no BLS_API_KEY)")
        print()
        print("  IMPORTANT: CUUR0000SA0 (raw headline CPI) is the primary")
        print("  series used by surprises.py. Without it, surprises will")
        print("  fall back to CPILFESL (Core CPI, FRED). That is fine for")
        print("  testing, but raw CPI is the 'official' headline number.")

    # ── Path 3: VIX / MOVE into vol_indices (requires yfinance) ──
    print("\n── Vol indices (^VIX, ^MOVE) — Path 3 ───────────────────────────")
    try:
        _fetch_with_retry(lambda _: fetch_vol_index("^VIX"), "^VIX", "^VIX (VIX)")
        time.sleep(0.5)
        _fetch_with_retry(lambda _: fetch_vol_index("^MOVE"), "^MOVE", "^MOVE (Treasury vol)")
    except Exception as exc:
        print(f"  ⚠  Vol indices skipped (install yfinance and retry): {exc}")

    # ── Summary ──
    print("\n" + "=" * 60)
    total_ok  = fred_ok + (bls_ok if has_bls_key else len(BLS_SERIES))
    total_all = len(FRED_SERIES) + len(BLS_SERIES)  # vol_indices tracked separately
    print(f"  Done. {total_ok}/{total_all} series populated.")

    if fred_ok == len(FRED_SERIES):
        print()
        print("  You can now run:")
        print("    python3 -m mini_hedge.transforms   # signals snapshot")
        print("    python3 -m mini_hedge.surprises    # CPI surprise table")
        print("    jupyter notebook notebooks/02_derived_signals.ipynb")
        print("    jupyter notebook notebooks/03_market_reactions.ipynb")

    print("=" * 60)


if __name__ == "__main__":
    force_refetch = "--force" in sys.argv
    if force_refetch:
        print("  --force flag: re-fetching all series even if already in DB.")
    main(force=force_refetch)
