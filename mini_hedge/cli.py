"""CLI entry point — commands for fetching and displaying economic data."""

import sys
from pathlib import Path

# Running this file directly (e.g. PyCharm Run on cli.py) sets sys.path[0] to
# mini_hedge/, so `import mini_hedge.*` fails. Put repo root on path first.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from datetime import datetime

from mini_hedge.config import (
    FRED_API_KEY,
    DEFAULT_FETCH_MONTHS,
    DEFAULT_DISPLAY_MONTHS,
    FETCH_FULL_HISTORY,
)
from mini_hedge import fetchers
from mini_hedge.transforms import signals_snapshot, SERIES_MAP

USAGE = """
Usage: econ.py <command> [N]

Commands:
    snapshot          Morning briefing — latest value, MoM%, YoY%, Z-score
                      for every series in SERIES_MAP (currently {n} indicators)
    fetch             Re-fetch all series from FRED / BLS into the database
    cpi [N]           Raw CPI-U history (BLS), last N rows
    core-cpi [N]      Core CPI history (FRED), last N rows
    fed-rate [N]      Fed Funds Rate history (FRED), last N rows
    unemployment [N]  Unemployment Rate history (FRED), last N rows
    yield-curve [N]   10Y−2Y Yield Curve history (FRED), last N rows
    treasury [N]      10Y Treasury Yield history (FRED), last N rows
    fetch-vol         Download ^VIX and ^MOVE into vol_indices (needs yfinance)
    vol [TICKER] [N]  Last N rows from vol_indices (default ^VIX)

To add a new indicator: add it to SERIES_MAP in transforms.py and run
  python3 scripts/bootstrap_db.py
The snapshot will pick it up automatically.
"""


# ── Individual series printers ────────────────────────────────────────────────

def _print_series(label, series_id, source, n):
    """Read from local DB; warn if empty."""
    from mini_hedge import storage
    import pandas as pd

    print(f"\n{'='*52}")
    print(f"  {label}  ({source}: {series_id})")
    print(f"{'='*52}")

    df = storage.query_series(series_id)
    if df.empty:
        print(f"  ✗  No data in local database.")
        print(f"     Run:  python3 scripts/bootstrap_db.py")
        return

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date", ascending=False).head(n)
    for row in df.itertuples():
        note = f"  ⚠ preliminary" if getattr(row, "footnotes", "") else ""
        print(f"  {row.date.strftime('%Y-%m-%d')}   {row.value}{note}")
    print(f"\n  ({len(df)} rows shown  |  run bootstrap_db.py to refresh)")


def _print_fred(label, series_id, n): _print_series(label, series_id, "FRED", n)
def _print_bls(label, series_id, n):  _print_series(label, series_id, "BLS",  n)


# ── Snapshot — driven entirely by SERIES_MAP ──────────────────────────────────

def cmd_snapshot():
    """
    Print the morning briefing table: FRED/BLS series in SERIES_MAP plus VIX/MOVE (vol_indices).

    Reading from the local SQLite database — no API calls needed.
    Run 'python3 scripts/bootstrap_db.py' first if any series are missing.
    """
    snap = signals_snapshot()
    print(f"\n{'='*68}")
    print(f"  US Economic Snapshot  —  {datetime.today().strftime('%Y-%m-%d %H:%M')}")
    print(f"  {len(snap)} rows  |  macro: SERIES_MAP + vol: VIX/MOVE")
    print(f"{'='*68}")

    if 'Error' in snap.columns:
        ok_rows  = snap[snap['Error'].isna()].drop(columns=['Error'])
        err_rows = snap[snap['Error'].notna()]
    else:
        ok_rows  = snap
        err_rows = snap.iloc[0:0]

    if not ok_rows.empty:
        # Column widths
        ind_w = max(ok_rows['Indicator'].str.len().max(), 12)
        print(f"\n  {'Indicator':<{ind_w}}  {'Source':6}  {'As of':12}  {'Value':>10}  {'MoM/1D Δ%':>10}  {'YoY/252D Δ%':>12}  {'Z-Score':>8}")
        print(f"  {'-'*ind_w}  {'------':6}  {'----------':12}  {'----------':>10}  {'----------':>10}  {'------------':>12}  {'-------':>8}")
        for _, row in ok_rows.iterrows():
            val    = f"{row['Value']:>10.3f}"  if row['Value']    is not None else f"{'—':>10}"
            short  = f"{row['Short Δ%']:>10.3f}" if row['Short Δ%'] is not None else f"{'—':>10}"
            long_  = f"{row['Long Δ%']:>12.3f}"  if row['Long Δ%']  is not None else f"{'—':>12}"
            z      = f"{row['Z-Score']:>8.2f}"   if row['Z-Score']  is not None else f"{'—':>8}"
            print(f"  {row['Indicator']:<{ind_w}}  {row['Source']:6}  {row['As of']:12}  {val}  {short}  {long_}  {z}")

    if not err_rows.empty:
        print(f"\n  ── Missing / empty (fetch to add) ─────────────────────────")
        for _, row in err_rows.iterrows():
            hint = row.get("Error", "")
            if str(row.get("Source")) == "vol_idx":
                extra = f" ({hint})" if hint else ""
                print(f"  ✗  {row['Indicator']:30s}  vol_indices{extra}")
            else:
                print(f"  ✗  {row['Indicator']:30s}  not in database — run bootstrap_db.py")

    print(f"\n  To refresh:  python3 scripts/bootstrap_db.py")
    print(f"  Vol indices: python -m mini_hedge.cli fetch-vol")
    print(f"  To add more macro: edit SERIES_MAP in mini_hedge/transforms.py")
    print()


# ── Fetch all ─────────────────────────────────────────────────────────────────

def cmd_fetch():
    """Re-fetch every series in SERIES_MAP from FRED / BLS."""
    print("Fetching all series...\n")
    for sid, (label, source) in SERIES_MAP.items():
        try:
            if source == "BLS":
                df = fetchers.fetch_bls(sid)
            else:
                df = fetchers.fetch_fred(sid)
            print(f"  ✓  {sid:20s}  {label}  ({len(df):,} rows)")
        except Exception as e:
            print(f"  ✗  {sid:20s}  {label}  ERROR: {e}")
    print()


# ── Individual commands ───────────────────────────────────────────────────────

def cmd_cpi(n):          _print_bls("CPI — All Urban Consumers", "CUUR0000SA0", n)
def cmd_core_cpi(n):     _print_fred("Core CPI — Ex Food & Energy", "CPILFESL", n)
def cmd_fed_rate(n):     _print_fred("Federal Funds Rate", "FEDFUNDS", n)
def cmd_unemployment(n): _print_fred("Unemployment Rate", "UNRATE", n)
def cmd_yield_curve(n):  _print_fred("Yield Curve (10Y − 2Y)", "T10Y2Y", n)
def cmd_treasury(n):     _print_fred("10Y Treasury Yield", "DGS10", n)


def cmd_fetch_vol():
    """Fetch ^VIX and ^MOVE into SQLite ``vol_indices``."""
    from mini_hedge.fetchers import fetch_vol_index

    print("Fetching volatility indices into vol_indices...\n")
    for t, name in (("^VIX", "CBOE VIX"), ("^MOVE", "ICE MOVE")):
        try:
            df = fetch_vol_index(t)
            print(f"  ✓  {t:8s}  {name}  ({len(df):,} rows)")
        except Exception as e:
            print(f"  ✗  {t:8s}  {name}  ERROR: {e}")
    print()


def cmd_vol(ticker: str, n: int):
    """Print last n rows of a vol index from local DB."""
    from mini_hedge import storage
    import pandas as pd

    print(f"\n{'='*52}")
    print(f"  Vol index: {ticker}")
    print(f"{'='*52}")
    df = storage.query_vol_index(ticker, last_n=max(n, 1))
    if df.empty:
        print("  No rows — run:  python3 -m mini_hedge.cli fetch-vol")
        print("       or:  python3 scripts/bootstrap_db.py")
        return
    df["date"] = pd.to_datetime(df["date"])
    tail = df.sort_values("date", ascending=False).head(n)
    for row in tail.itertuples():
        print(f"  {row.date.strftime('%Y-%m-%d')}   {row.close:.4f}")
    print(f"\n  ({len(tail)} rows shown)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(USAGE.format(n=len(SERIES_MAP)))
        sys.exit(1)

    cmd = args[0]
    default_n = DEFAULT_DISPLAY_MONTHS if FETCH_FULL_HISTORY else DEFAULT_FETCH_MONTHS
    # Only parse [N] for commands that use it. `vol` has its own argument shape.
    n = int(args[1]) if (len(args) > 1 and args[1].isdigit()) else default_n

    if cmd == "fetch-vol":
        if not FRED_API_KEY:
            print("Note: FRED_API_KEY is used if ^VIX yfinance fails; set it in .env.")
        cmd_fetch_vol()

    elif cmd == "vol":
        if len(args) == 2 and args[1].isdigit():
            ticker, n_vol = "^VIX", int(args[1])
        elif len(args) >= 2:
            ticker = args[1]
            n_vol = int(args[2]) if len(args) > 2 and args[2].isdigit() else default_n
        else:
            ticker, n_vol = "^VIX", default_n
        cmd_vol(ticker, n_vol)

    elif cmd == "snapshot":
        cmd_snapshot()

    elif cmd == "fetch":
        if not FRED_API_KEY:
            print("Error: FRED_API_KEY not set. Add it to your .env file.")
            sys.exit(1)
        cmd_fetch()

    elif cmd == "cpi":          cmd_cpi(n)
    elif cmd == "core-cpi":     cmd_core_cpi(n)
    elif cmd == "fed-rate":     cmd_fed_rate(n)
    elif cmd == "unemployment":  cmd_unemployment(n)
    elif cmd == "yield-curve":  cmd_yield_curve(n)
    elif cmd == "treasury":     cmd_treasury(n)

    else:
        print(f"Unknown command: '{cmd}'")
        print(USAGE.format(n=len(SERIES_MAP)))
        sys.exit(1)


if __name__ == "__main__":
    main()
