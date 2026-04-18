"""
Week 2 — Market Price Data: prices.py

To measure whether a CPI surprise actually moves markets, we need price data
for the instruments we plan to trade: TLT (Treasury bonds) and SPY (S&P 500).

We use two approaches:
  1. 10Y Treasury Yield (DGS10) — already in your database, daily going back to 1962.
     When yield RISES → bonds (TLT) FALL. When yield FALLS → TLT RISES.
     This gives us the same directional signal without needing TLT prices directly.

  2. CSV loader — once you download TLT/SPY price history from Yahoo Finance
     (finance.yahoo.com → search ticker → Historical Data → Download), load it here.

NOTE: To use yfinance directly (auto-download), install it on your local machine:
      pip install yfinance
      Then uncomment the fetch_yfinance() function at the bottom of this file.
      It cannot run in all environments due to network restrictions.
"""

import pandas as pd
import numpy as np
from pathlib import Path

from mini_hedge import storage
from mini_hedge.config import PROJECT_ROOT


# ── 1. 10Y Treasury Yield (already in your DB) ───────────────────────────────

def load_10y_yield() -> pd.DataFrame:
    """
    Load the 10-Year Treasury Yield (DGS10) from your database.

    This is your PRIMARY bond market proxy. The relationship to TLT:
      Yield UP   → bond prices DOWN → TLT DOWN  (hot CPI / hawkish Fed)
      Yield DOWN → bond prices UP   → TLT UP    (cool CPI / dovish Fed)

    Daily frequency. Goes back to 1962-01-02 in your database.
    Returns DataFrame sorted oldest-first with columns: date, yield_10y
    """
    df = storage.query_series("DGS10")
    if df.empty:
        raise ValueError("DGS10 not in database. Run: fetchers.fetch_fred('DGS10')")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df.rename(columns={"value": "yield_10y"})
    return df[["date", "yield_10y"]]


def yield_to_price_proxy(df: pd.DataFrame, yield_col: str = "yield_10y") -> pd.DataFrame:
    """
    Convert yield changes to approximate bond price direction.

    For a 10-year bond, a +0.01% (1 basis point) rise in yield ≈ -0.09% fall in price.
    This is called 'duration' — the price sensitivity of a bond to yield changes.
    TLT has a duration of about 17 years, so it's even more sensitive.

    This function adds:
      yield_chg_1d  — yield change vs previous day (in percentage points)
      price_dir     — +1 (yield fell, bonds up) or -1 (yield rose, bonds down)
      price_approx  — approximate TLT % move (yield_chg × -17 for TLT duration)
    """
    df = df.copy()
    df["yield_chg_1d"] = df[yield_col].diff(1)
    df["price_dir"] = np.sign(-df["yield_chg_1d"])   # invert: yield up = price down
    df["price_approx_pct"] = -df["yield_chg_1d"] * 17  # TLT duration ≈ 17 years
    return df


# ── 2. CPI Release Calendar ───────────────────────────────────────────────────

# Historical BLS CPI release dates — the actual day the number is published.
# The BLS publishes CPI around the 10th-13th of the month following the reference month.
# Source: https://www.bls.gov/schedule/news_release/cpi.htm
# Add future dates as they are announced.

CPI_RELEASE_DATES = [
    # 2012  (BLS released ~15th–20th of month in this era; verify at bls.gov/schedule)
    "2012-01-19", "2012-02-17", "2012-03-16", "2012-04-13", "2012-05-15",
    "2012-06-14", "2012-07-17", "2012-08-15", "2012-09-14", "2012-10-16",
    "2012-11-15", "2012-12-14",
    # 2013  (Oct delayed to 2013-10-30 due to US government shutdown)
    "2013-01-16", "2013-02-21", "2013-03-15", "2013-04-16", "2013-05-16",
    "2013-06-18", "2013-07-16", "2013-08-15", "2013-09-17", "2013-10-30",
    "2013-11-20", "2013-12-17",
    # 2014
    "2014-01-16", "2014-02-20", "2014-03-18", "2014-04-15", "2014-05-15",
    "2014-06-17", "2014-07-22", "2014-08-19", "2014-09-17", "2014-10-22",
    "2014-11-20", "2014-12-17",
    # 2015
    "2015-01-16", "2015-02-26", "2015-03-24", "2015-04-17", "2015-05-22",
    "2015-06-18", "2015-07-17", "2015-08-19", "2015-09-16", "2015-10-15",
    "2015-11-17", "2015-12-15",
    # 2016
    "2016-01-20", "2016-02-19", "2016-03-16", "2016-04-14", "2016-05-17",
    "2016-06-16", "2016-07-15", "2016-08-16", "2016-09-16", "2016-10-18",
    "2016-11-17", "2016-12-15",
    # 2017
    "2017-01-18", "2017-02-15", "2017-03-15", "2017-04-14", "2017-05-12",
    "2017-06-14", "2017-07-14", "2017-08-11", "2017-09-14", "2017-10-13",
    "2017-11-15", "2017-12-13",
    # 2018
    "2018-01-12", "2018-02-14", "2018-03-13", "2018-04-11", "2018-05-10",
    "2018-06-12", "2018-07-12", "2018-08-10", "2018-09-13", "2018-10-11",
    "2018-11-14", "2018-12-12",
    # 2019
    "2019-01-11", "2019-02-13", "2019-03-12", "2019-04-10", "2019-05-10",
    "2019-06-12", "2019-07-11", "2019-08-13", "2019-09-12", "2019-10-10",
    "2019-11-13", "2019-12-11",
    # 2020
    "2020-01-14", "2020-02-13", "2020-03-11", "2020-04-10", "2020-05-12",
    "2020-06-10", "2020-07-14", "2020-08-12", "2020-09-11", "2020-10-13",
    "2020-11-12", "2020-12-10",
    # 2021
    "2021-01-13", "2021-02-10", "2021-03-10", "2021-04-13", "2021-05-12",
    "2021-06-10", "2021-07-13", "2021-08-11", "2021-09-14", "2021-10-13",
    "2021-11-10", "2021-12-10",
    # 2022
    "2022-01-12", "2022-02-10", "2022-03-10", "2022-04-12", "2022-05-11",
    "2022-06-10", "2022-07-13", "2022-08-10", "2022-09-13", "2022-10-13",
    "2022-11-10", "2022-12-13",
    # 2023
    "2023-01-12", "2023-02-14", "2023-03-14", "2023-04-12", "2023-05-10",
    "2023-06-13", "2023-07-12", "2023-08-10", "2023-09-13", "2023-10-12",
    "2023-11-14", "2023-12-12",
    # 2024
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15",
    "2024-06-12", "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10",
    "2024-11-13", "2024-12-11",
    # 2025
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13",
    "2025-06-11", "2025-07-15", "2025-08-12", "2025-09-10", "2025-10-15",
    "2025-11-13", "2025-12-10",
    # 2026 (extend when BLS publishes exact dates; ~2nd week each month)
    "2026-01-15", "2026-02-12", "2026-03-11", "2026-04-10", "2026-05-13",
    "2026-06-10", "2026-07-15", "2026-08-12", "2026-09-10", "2026-10-14",
    "2026-11-12", "2026-12-10",
]


def get_release_dates(consensus_csv: str = None) -> pd.Series:
    """
    Return CPI release dates as a sorted pandas Series of Timestamps.

    If a consensus CSV path is provided and the file exists, dates from
    the CSV are merged with the hardcoded list — CSV dates take priority
    for any overlapping year-months. This means investing.com release
    dates (which are exact) override the hardcoded estimates for 2012-2019.

    Parameters
    ----------
    consensus_csv : str, optional
        Path to cpi_consensus.csv. If None, uses only the hardcoded list.
        Relative paths resolve from the project root.
    """
    base = pd.to_datetime(CPI_RELEASE_DATES)

    if consensus_csv is None:
        return base.sort_values()

    csv_path = Path(consensus_csv)
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / consensus_csv
    if not csv_path.exists():
        return base.sort_values()

    try:
        csv_df = pd.read_csv(csv_path)
        col = next((c for c in ["release_date", "date"] if c in csv_df.columns), None)
        if col is None:
            return base.sort_values()
        # investing.com uses "Apr 10, 2026"; manual rows may be ISO — need mixed parsing
        csv_dates = pd.to_datetime(csv_df[col], format="mixed", errors="coerce").dropna()
        # Build year-month index for both; CSV dates win on overlap
        base_df = pd.DataFrame({"date": base, "ym": base.to_period("M")})
        csv_df2 = pd.DataFrame({"date": csv_dates, "ym": csv_dates.dt.to_period("M")})
        merged = pd.concat([base_df, csv_df2]).sort_values("ym")
        # Keep last occurrence per year-month (CSV date, added second, wins)
        merged = merged.drop_duplicates(subset="ym", keep="last")
        return pd.DatetimeIndex(merged["date"]).sort_values()
    except Exception:
        return base.sort_values()


def _release_dates_index(consensus_csv: str | None = "data/cpi_consensus.csv"):
    """Prefer release dates merged from ``cpi_consensus.csv`` when that file exists
    (investing.com / Cleveland Fed), so new months (e.g. 2027+) appear without
    editing ``CPI_RELEASE_DATES``. Falls back to the hardcoded list only."""
    if consensus_csv:
        p = Path(consensus_csv)
        if not p.is_absolute():
            p = PROJECT_ROOT / consensus_csv
        if p.exists():
            return get_release_dates(consensus_csv)
    return get_release_dates(None)


# ── 3. Align yield data to release dates ─────────────────────────────────────

def yield_around_releases(
    lookback_days: int = 1,
    forward_days: int = 5,
    consensus_csv: str | None = "data/cpi_consensus.csv",
) -> pd.DataFrame:
    """
    For each CPI release date, capture the 10Y yield change over multiple windows.

    This is the core of the Week 3 event study. For every release:
      - yield_day0      : yield ON the release day
      - yield_chg_1d    : yield change on release day vs day before
      - yield_chg_3d    : cumulative yield change over 3 trading days
      - yield_chg_5d    : cumulative yield change over 5 trading days
      - price_dir_1d    : bond price direction on release day (+1 up / -1 down)

    Parameters
    ----------
    lookback_days  : days before release to use as the baseline (default 1)
    forward_days   : max days forward to measure (default 5)

    consensus_csv : str | None, optional
        If the file exists (default ``data/cpi_consensus.csv``), its release dates
        are merged with the hardcoded calendar — **CSV wins** on overlapping
        year-months and can add **future** release months (e.g. 2027+).

    Returns DataFrame indexed by release date.
    """
    yields = load_10y_yield().set_index("date")["yield_10y"].sort_index()
    release_dates = _release_dates_index(consensus_csv)

    rows = []
    for rel_date in release_dates:
        # Find the actual trading day on or after the release
        trading_days = yields.loc[rel_date:].index
        if len(trading_days) < 2:
            continue
        day0 = trading_days[0]

        # Baseline: last available yield BEFORE the release
        before = yields.loc[:rel_date - pd.Timedelta(days=1)]
        if before.empty:
            continue
        baseline_yield = before.iloc[-1]

        # Yield on release day
        y0 = yields.loc[day0]

        # Forward yield readings
        def fwd_yield(n):
            fwd_days = yields.loc[day0:].index
            if len(fwd_days) > n:
                return yields.loc[fwd_days[n]]
            return np.nan

        chg_1d = round(y0 - baseline_yield, 4)
        chg_3d = fwd_yield(2)   # None → np.nan if window not closed yet
        chg_5d = fwd_yield(4)

        chg_3d = round(chg_3d - baseline_yield, 4) if not np.isnan(chg_3d) else np.nan
        chg_5d = round(chg_5d - baseline_yield, 4) if not np.isnan(chg_5d) else np.nan

        row = {
            "release_date":    rel_date,
            "yield_baseline":  round(baseline_yield, 4),
            "yield_day0":      round(y0, 4),
            "yield_chg_1d":    chg_1d,
            "yield_chg_3d":    chg_3d,
            "yield_chg_5d":    chg_5d,
            # Bond price direction — opposite to yield direction
            "price_dir_1d":    int(np.sign(baseline_yield - y0)),
            "price_dir_3d":    int(np.sign(-chg_3d)) if not np.isnan(chg_3d) else pd.NA,
            "price_dir_5d":    int(np.sign(-chg_5d)) if not np.isnan(chg_5d) else pd.NA,
            # Window flags — False means the forward window hasn't closed yet.
            # ALWAYS filter on these before computing win rates or expectancy.
            # A NaN yield_chg is NOT a loss — it is an incomplete observation.
            "window_1d_complete": not np.isnan(chg_1d),
            "window_3d_complete": not np.isnan(chg_3d),
            "window_5d_complete": not np.isnan(chg_5d),
        }
        rows.append(row)

    return pd.DataFrame(rows)


# ── 4. Safe event filter — always use this before computing win rates ─────────

def complete_events(events: pd.DataFrame, horizon: str = "1d") -> pd.DataFrame:
    """
    Filter yield events to only those where the forward window has fully closed.

    A NaN yield_chg is NOT a loss — it means the market data doesn't exist yet.
    Including incomplete windows in a win-rate calculation silently understates
    performance (incomplete trades look like wrong calls). Always call this
    before any backtest aggregation.

    Parameters
    ----------
    events : pd.DataFrame
        Output of yield_around_releases().
    horizon : str
        '1d', '3d', or '5d' — which forward window to require complete.

    Returns
    -------
    Filtered DataFrame containing only fully observed events for that horizon.

    Usage
    -----
        events = yield_around_releases()
        ev1d = complete_events(events, '1d')   # for 1-day backtest
        ev5d = complete_events(events, '5d')   # for 5-day backtest
    """
    col = f"window_{horizon}_complete"
    if col not in events.columns:
        raise ValueError(
            f"Column '{col}' not found. "
            f"Re-run yield_around_releases() to get the updated output."
        )
    complete = events[events[col] == True].copy()
    n_dropped = len(events) - len(complete)
    if n_dropped > 0:
        import warnings
        warnings.warn(
            f"complete_events({horizon!r}): dropped {n_dropped} incomplete "
            f"observation(s) — forward window has not closed yet. "
            f"These are NOT losses; re-run after market closes to include them.",
            stacklevel=2,
        )
    return complete.reset_index(drop=True)


# ── 5. CSV loader for TLT / SPY ───────────────────────────────────────────────

def load_price_csv(filepath: str, ticker: str) -> pd.DataFrame:
    """
    Load price history downloaded from Yahoo Finance as a CSV.

    How to download (do this once on your local machine):
      1. Go to finance.yahoo.com
      2. Search for TLT (or SPY)
      3. Click 'Historical Data'
      4. Set time period to 'Max'
      5. Click 'Download'
      6. Save to: Mini_Hedge/data/TLT.csv  (or SPY.csv)

    Then call:
        tlt = load_price_csv("data/TLT.csv", "TLT")

    Returns DataFrame with columns: date, open, high, low, close, volume, ticker
    """
    path = Path(filepath)
    if not path.is_absolute():
        path = PROJECT_ROOT / filepath

    if not path.exists():
        raise FileNotFoundError(
            f"Price file not found: {path}\n"
            f"Download from Yahoo Finance:\n"
            f"  https://finance.yahoo.com/quote/{ticker}/history\n"
            f"  Save to: {PROJECT_ROOT / 'data' / (ticker + '.csv')}"
        )

    df = pd.read_csv(path)
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = ticker
    df = df.sort_values("date").reset_index(drop=True)

    # Keep standard columns
    keep = [c for c in ["date", "open", "high", "low", "close", "adj_close", "volume", "ticker"]
            if c in df.columns]
    return df[keep]


def price_around_releases(
    price_df: pd.DataFrame,
    ticker: str,
    consensus_csv: str | None = "data/cpi_consensus.csv",
) -> pd.DataFrame:
    """
    For each CPI release date, compute price returns over multiple windows.

    Returns DataFrame with columns:
      release_date, close_baseline, ret_1d, ret_3d, ret_5d, direction_1d
    """
    prices = price_df.set_index("date")["close"].sort_index()
    release_dates = _release_dates_index(consensus_csv)

    rows = []
    for rel_date in release_dates:
        before = prices.loc[:rel_date - pd.Timedelta(days=1)]
        after  = prices.loc[rel_date:]
        if before.empty or len(after) < 2:
            continue

        baseline = before.iloc[-1]

        def fwd_ret(n):
            if len(after) > n:
                return round((after.iloc[n] / baseline - 1) * 100, 4)
            return np.nan

        r0 = fwd_ret(0)
        rows.append({
            "release_date":    rel_date,
            "ticker":          ticker,
            "close_baseline":  round(baseline, 2),
            "ret_1d":          r0,
            "ret_3d":          fwd_ret(2),
            "ret_5d":          fwd_ret(4),
            "direction_1d":    int(np.sign(r0)) if pd.notna(r0) else 0,
        })

    return pd.DataFrame(rows)


# ── 5. yfinance (install locally to use) ─────────────────────────────────────

def fetch_yfinance(ticker: str, start: str = "2002-07-26") -> pd.DataFrame:
    """
    Download price history using yfinance (requires: pip install yfinance).

    TLT started trading on 2002-07-26, so that's the default start date.
    For SPY use start='1993-01-29'.

    Usage (on your local machine after pip install yfinance):
        from mini_hedge.prices import fetch_yfinance
        tlt = fetch_yfinance("TLT")
        spy = fetch_yfinance("SPY", start="1993-01-29")
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "yfinance is not installed.\n"
            "Run on your local machine: pip install yfinance\n"
            "Or use load_price_csv() with a manually downloaded CSV instead."
        )
    raw = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    raw = raw.reset_index()
    raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in raw.columns]
    raw["ticker"] = ticker
    return raw[["date", "open", "high", "low", "close", "volume", "ticker"]]


if __name__ == "__main__":
    print("Loading 10Y yield around CPI release dates...\n")
    df = yield_around_releases()
    print(df.tail(10).to_string(index=False))
    print(f"\n{len(df)} CPI release dates with yield data.")
