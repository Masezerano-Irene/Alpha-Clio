"""
Week 2 — Derived Signals: transforms.py

Converts raw economic numbers into signals quant traders actually use.
Raw CPI of 326.785 tells you nothing. These transforms tell you:
  - How fast is inflation changing? (MoM %)
  - What is the annual trend?      (YoY %)
  - How unusual is this reading?   (Z-score)
  - What is the smoothed trend?    (moving averages)
"""

import pandas as pd
import numpy as np

from mini_hedge import storage


# ── 1. Load from database ────────────────────────────────────────────────────

def load_series(series_id: str) -> pd.DataFrame:
    """
    Load a series from the SQLite database, sorted oldest-first.

    Returns DataFrame with columns: date, value, series_id
    Always call this before applying transforms so data is in chronological order.
    """
    df = storage.query_series(series_id)
    if df.empty:
        raise ValueError(
            f"\n{'='*60}\n"
            f"  Empty series: '{series_id}'\n"
            f"  The local database has no data for this series.\n"
            f"\n"
            f"  Fix: run the bootstrap script ONCE to populate the DB:\n"
            f"    cd Mini_Hedge\n"
            f"    python3 scripts/bootstrap_db.py\n"
            f"\n"
            f"  Or fetch just this one series:\n"
            f"    from mini_hedge.fetchers import fetch_fred, fetch_bls\n"
            f"    fetch_fred('{series_id}')   # FRED series\n"
            f"    fetch_bls('{series_id}')    # BLS series (CUUR0000SA0)\n"
            f"\n"
            f"  Make sure your .env file has FRED_API_KEY set.\n"
            f"{'='*60}"
        )
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "value", "series_id"]]


# ── 2. Core transforms ────────────────────────────────────────────────────────

def mom_pct(df: pd.DataFrame, value_col: str = "value") -> pd.DataFrame:
    """
    Month-over-Month percentage change.

    This is the number the Fed and news headlines quote: "CPI rose 0.4% in March."
    Formula: (current - previous) / previous × 100

    Why it matters: shows the SPEED of change — is inflation accelerating or slowing?
    A reading that was rising 0.5%/month and is now 0.2%/month is DECELERATING
    even though prices are still going up. The bond market trades on this direction.
    """
    df = df.copy()
    df["mom_pct"] = df[value_col].pct_change(periods=1) * 100
    return df


def yoy_pct(df: pd.DataFrame, value_col: str = "value") -> pd.DataFrame:
    """
    Year-over-Year percentage change (12-period lag for monthly series).

    This is "annual inflation": how much higher are prices than a year ago?
    Formula: (current - same_month_last_year) / same_month_last_year × 100

    Why it matters: removes seasonality. January is always a bit different from July
    for structural reasons. YoY compares Jan-to-Jan, removing that noise.
    The Fed's 2% inflation target is expressed as a YoY number.
    """
    df = df.copy()
    df["yoy_pct"] = df[value_col].pct_change(periods=12) * 100
    return df


def rolling_zscore(
    df: pd.DataFrame,
    value_col: str = "value",
    window: int = 60,
    min_periods: int = 24,
) -> pd.DataFrame:
    """
    Rolling Z-score: how unusual is this reading compared to the past {window} months?

    Formula: (current - rolling_mean) / rolling_std

    Why it matters: context. A CPI MoM of +0.4% means very different things
    depending on history. In the 1970s it was normal. In 2015 it was high.
    The Z-score standardizes across time periods:
      Z = 0    → perfectly average reading
      Z = +1   → 1 standard deviation above average (top ~16%)
      Z = +2   → 2 std devs above (top ~2.5%) — market-moving territory
      Z = -1   → 1 std dev below average (bottom ~16%)

    Default window of 60 months (5 years) captures a full economic cycle.
    """
    df = df.copy()
    roll = df[value_col].rolling(window=window, min_periods=min_periods)
    roll_std = roll.std().replace(0, np.nan)
    df["zscore"] = (df[value_col] - roll.mean()) / roll_std
    return df


def rolling_mean(
    df: pd.DataFrame,
    value_col: str = "value",
    window: int = 12,
    min_periods: int = 3,
) -> pd.DataFrame:
    """
    Rolling moving average — smooths out monthly noise to reveal the true trend.

    Why it matters: a single month's reading can be distorted by one-off events
    (hurricanes, supply chain shocks). The 3-month moving average shows whether
    the underlying trend is up, down, or flat regardless of month-to-month noise.
    """
    df = df.copy()
    df[f"ma_{window}m"] = df[value_col].rolling(window=window, min_periods=min_periods).mean()
    return df


# ── 3. Apply all at once ──────────────────────────────────────────────────────

def add_all_transforms(
    df: pd.DataFrame,
    value_col: str = "value",
    zscore_window: int = 60,
) -> pd.DataFrame:
    """
    Apply every transform to the DataFrame in one call.

    Returns DataFrame with these new columns:
      mom_pct      — Month-over-Month % change
      yoy_pct      — Year-over-Year % change
      zscore       — Rolling z-score of the raw value (vs 60m window)
      ma_3m        — 3-month moving average (short trend)
      ma_12m       — 12-month moving average (long trend)
    """
    df = mom_pct(df, value_col)
    df = yoy_pct(df, value_col)
    df = rolling_zscore(df, value_col, window=zscore_window)
    df = rolling_mean(df, value_col, window=3)
    df = rolling_mean(df, value_col, window=12)
    return df


# Daily series (e.g. DGS10): same column names but 1d / ~252d yoy / rolling z on ~5y window
_DAILY_TRADING_YOY = 252
_DAILY_ZSCORE_WINDOW = 1260  # ~5 years of trading days


def add_daily_transforms(
    df: pd.DataFrame,
    value_col: str = "value",
    zscore_window: int = _DAILY_ZSCORE_WINDOW,
) -> pd.DataFrame:
    """Transforms for daily data (10Y yield). Uses trading-day lags, not calendar months."""
    df = df.copy()
    df["mom_pct"] = df[value_col].pct_change(periods=1) * 100
    df["yoy_pct"] = df[value_col].pct_change(periods=_DAILY_TRADING_YOY) * 100
    roll = df[value_col].rolling(window=zscore_window, min_periods=_DAILY_TRADING_YOY)
    roll_std = roll.std().replace(0, np.nan)
    df["zscore"] = (df[value_col] - roll.mean()) / roll_std
    df = rolling_mean(df, value_col, window=63, min_periods=21)
    df = rolling_mean(df, value_col, window=252, min_periods=63)
    return df


# ── Path 3 — Realized volatility & IV–RV style spreads ──────────────────────

def realized_volatility(
    prices: pd.DataFrame,
    window_days: int = 20,
    annualize: bool = True,
    date_col: str = "date",
    price_col: str = "close",
    out_col: str = "rv_pct",
) -> pd.DataFrame:
    """
    Close-to-close realized volatility on daily prices.

    Uses log returns; when ``annualize=True`` (default):
        std(log_ret, window) * sqrt(252) * 100
    so the result is in **percent** annualized, comparable to VIX level.

    Parameters
    ----------
    prices : DataFrame
        Must contain ``date`` and a price column (default ``close``).
    window_days : int
        Rolling window length in **trading days** (not calendar).
    """
    df = prices.sort_values(date_col).copy()
    df[date_col] = pd.to_datetime(df[date_col])
    px = pd.to_numeric(df[price_col], errors="coerce")
    log_ret = np.log(px / px.shift(1))
    roll = log_ret.rolling(window=window_days, min_periods=max(5, window_days // 4))
    vol = roll.std()
    if annualize:
        vol = vol * np.sqrt(252) * 100.0
    else:
        vol = vol * 100.0
    df[out_col] = vol
    return df


def equity_iv_minus_rv(
    vix_df: pd.DataFrame,
    rv_spy_df: pd.DataFrame,
    date_col: str = "date",
    vix_close_col: str = "close",
    rv_col: str = "rv_pct",
    out_col: str = "vix_minus_rv_spy",
) -> pd.DataFrame:
    """Merge VIX level with SPY realized vol; ``out_col`` = VIX − RV (both in % ann.)."""
    v = vix_df[[date_col, vix_close_col]].rename(columns={vix_close_col: "vix"})
    r = rv_spy_df[[date_col, rv_col]].rename(columns={rv_col: "rv_spy"})
    m = pd.merge(v, r, on=date_col, how="inner")
    m[out_col] = m["vix"] - m["rv_spy"]
    return m.sort_values(date_col).reset_index(drop=True)


def treasury_move_minus_scaled_rv(
    move_df: pd.DataFrame,
    rv_tlt_df: pd.DataFrame,
    date_col: str = "date",
    move_col: str = "close",
    rv_col: str = "rv_pct",
    rv_scale: float = 0.12,
    out_col: str = "move_minus_scaled_rv_tlt",
) -> pd.DataFrame:
    """
    MOVE (ICE BofA Treasury implied vol index) minus a **scaled** TLT realized vol.

    MOVE is not quoted in the same units as an equity-style annualized % price vol.
    ``rv_scale`` maps TLT ``rv_pct`` into a range comparable to MOVE for **charts
    and event studies** only — calibrate visually or from your own regression; do
    not treat the default as a physical identity.

    Default: ``out_col = MOVE - rv_tlt_pct * rv_scale`` with ``rv_scale=0.12``.
    """
    mv = move_df[[date_col, move_col]].rename(columns={move_col: "move"})
    r = rv_tlt_df[[date_col, rv_col]].rename(columns={rv_col: "rv_tlt"})
    m = pd.merge(mv, r, on=date_col, how="inner")
    m[out_col] = m["move"] - m["rv_tlt"] * rv_scale
    return m.sort_values(date_col).reset_index(drop=True)


def enrich_series(series_id: str, zscore_window: int = 60) -> pd.DataFrame:
    """
    One-shot convenience: load a series from the DB and apply all transforms.

    Usage:
        from mini_hedge.transforms import enrich_series
        cpi = enrich_series("CUUR0000SA0")   # BLS CPI
        core = enrich_series("CPILFESL")      # FRED Core CPI
        print(cpi[["date", "value", "mom_pct", "yoy_pct", "zscore"]].tail(12))
    """
    df = load_series(series_id)
    if series_id in _DAILY_SERIES:
        return add_daily_transforms(df, zscore_window=_DAILY_ZSCORE_WINDOW)
    return add_all_transforms(df, zscore_window=zscore_window)


# ── 4. Summary snapshot ───────────────────────────────────────────────────────

SERIES_MAP = {
    # ── Inflation ──────────────────────────────────────────────────────────────
    "CUUR0000SA0": ("CPI — All Urban Consumers",     "BLS"),
    "CPILFESL":    ("Core CPI — Ex Food & Energy",   "FRED"),
    # ── Fed / Rates ────────────────────────────────────────────────────────────
    "FEDFUNDS":    ("Federal Funds Rate",             "FRED"),
    "DGS10":       ("10Y Treasury Yield",             "FRED"),
    "T10Y2Y":      ("Yield Curve  (10Y − 2Y)",        "FRED"),   # negative = inverted = recession risk
    # ── Labour Market ──────────────────────────────────────────────────────────
    "UNRATE":      ("Unemployment Rate",              "FRED"),   # Fed dual mandate — pairs with CPI
    "DFEDTARU":    ("Fed Funds Target — Upper",       "FRED"),   # FOMC decision level (Path 3 scaffold)
}

# Series that need daily transforms instead of monthly
_DAILY_SERIES = {"DGS10", "T10Y2Y", "DFEDTARU"}


def _vol_index_snapshot_rows() -> list[dict]:
    """Latest VIX / MOVE from ``vol_indices`` (Path 3), with 1d and ~252d % change on level."""
    out = []
    for ticker, label in (("^VIX", "VIX (CBOE)"), ("^MOVE", "MOVE (ICE Treasury vol)")):
        try:
            df = storage.query_vol_index(ticker, last_n=400)
            if df.empty:
                out.append({
                    "Indicator": label,
                    "Source": "vol_idx",
                    "Error": "no rows — run: python -m mini_hedge.cli fetch-vol",
                })
                continue
            df = df.sort_values("date").reset_index(drop=True)
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else None
            short = (
                (float(latest["close"]) / float(prev["close"]) - 1.0) * 100.0
                if prev is not None
                else None
            )
            long_pct = None
            if len(df) > 252:
                c0 = float(df.iloc[-253]["close"])
                long_pct = (float(latest["close"]) / c0 - 1.0) * 100.0 if c0 else None
            z = None
            tail = df["close"].astype(float).iloc[-252:]
            if len(tail) >= 60 and tail.std() > 0:
                z = (float(latest["close"]) - tail.mean()) / tail.std()
            out.append({
                "Indicator":  label,
                "Source":     "vol_idx",
                "As of":      pd.Timestamp(latest["date"]).strftime("%Y-%m-%d"),
                "Value":      round(float(latest["close"]), 3),
                "Short Δ%":   round(short, 3) if short is not None else None,
                "Long Δ%":    round(long_pct, 3) if long_pct is not None else None,
                "Z-Score":    round(z, 3) if z is not None else None,
            })
        except Exception as e:
            out.append({"Indicator": label, "Source": "vol_idx", "Error": str(e)})
    return out


def signals_snapshot() -> pd.DataFrame:
    """
    Build a one-row-per-series summary table of the latest readings.

    Returns the most recent value, short- and long-horizon % changes (MoM/YoY for
    monthly series; 1d / ~252 trading days for daily DGS10), and Z-score.

    Appends **VIX** and **MOVE** (Path 3) from ``vol_indices`` when present.

    Usage:
        from mini_hedge.transforms import signals_snapshot
        snap = signals_snapshot()
        print(snap.to_string(index=False))
    """
    rows = []
    for series_id, (label, source) in SERIES_MAP.items():
        try:
            df = enrich_series(series_id)
            # For DGS10 (daily), get the most recent row; others are monthly
            latest = df.dropna(subset=["value"]).iloc[-1]
            rows.append({
                "Indicator":  label,
                "Source":     source,
                "As of":      latest["date"].strftime("%Y-%m-%d"),
                "Value":      round(latest["value"], 3),
                "Short Δ%":   round(latest["mom_pct"], 3) if pd.notna(latest["mom_pct"]) else None,
                "Long Δ%":    round(latest["yoy_pct"], 3) if pd.notna(latest["yoy_pct"]) else None,
                "Z-Score":    round(latest["zscore"],  3) if pd.notna(latest["zscore"])  else None,
            })
        except Exception as e:
            rows.append({"Indicator": label, "Source": source, "Error": str(e)})

    rows.extend(_vol_index_snapshot_rows())
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print("\n=== Signals Snapshot ===\n")
    snap = signals_snapshot()
    print(snap.to_string(index=False))
