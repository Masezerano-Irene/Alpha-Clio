"""
Path 3 — Event-study helpers: window returns and vol tags around macro dates.

Designed for CPI / NFP / FOMC rows with an ``event_date`` column. All returns are
**close-to-close %** from a baseline chosen as the last available close **strictly
before** ``event_date`` (T−1 style), through horizons measured on **trading rows**
on or after ``event_date``.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from mini_hedge import storage
from mini_hedge.transforms import realized_volatility


def forward_close_returns(
    prices: pd.DataFrame,
    events: pd.DataFrame,
    event_date_col: str = "event_date",
    date_col: str = "date",
    close_col: str = "close",
    horizons: tuple[int, ...] = (0, 1, 5),
) -> pd.DataFrame:
    """
    For each event, compute forward closes vs baseline (last close strictly before event).

    ``horizons`` are **0-based row offsets** on trading days on/after the first row
    with ``date >= event_date``. ``0`` = first session on/after the event calendar day.
    """
    px = prices[[date_col, close_col]].copy()
    px[date_col] = pd.to_datetime(px[date_col]).dt.normalize()
    px = px.sort_values(date_col).dropna(subset=[close_col]).reset_index(drop=True)

    rows = []
    for _, ev in events.iterrows():
        e = pd.to_datetime(ev[event_date_col]).normalize()
        before = px[px[date_col] < e]
        from_e = px[px[date_col] >= e]
        if before.empty or from_e.empty:
            continue
        base = float(before.iloc[-1][close_col])
        out = {event_date_col: e}
        for h in horizons:
            key = f"ret_h{h}"
            if len(from_e) > h:
                ch = float(from_e.iloc[h][close_col])
                out[key] = round((ch / base - 1.0) * 100.0, 4) if base else np.nan
            else:
                out[key] = np.nan
        rows.append(out)
    base_df = pd.DataFrame(rows)
    if base_df.empty:
        return base_df
    ev_dates = events.copy()
    ev_dates[event_date_col] = pd.to_datetime(ev_dates[event_date_col]).dt.normalize()
    merged = ev_dates.merge(base_df, on=event_date_col, how="left")
    return merged


def realized_vol_over_window(
    prices: pd.DataFrame,
    event_date: pd.Timestamp,
    start_offset: int = 0,
    end_offset: int = 5,
    date_col: str = "date",
    close_col: str = "close",
) -> float:
    """
    Annualized std of daily log returns from trading row ``start_offset`` through
    ``end_offset`` (inclusive) relative to the first row with ``date >= event_date``.
    Returns NaN if insufficient rows.
    """
    px = prices[[date_col, close_col]].copy()
    px[date_col] = pd.to_datetime(px[date_col]).dt.normalize()
    px = px.sort_values(date_col).reset_index(drop=True)
    e = pd.Timestamp(event_date).normalize()
    sub = px[px[date_col] >= e].iloc[start_offset : end_offset + 1]
    if len(sub) < 2:
        return float("nan")
    r = np.log(sub[close_col].astype(float) / sub[close_col].astype(float).shift(1))
    return float(r.std() * np.sqrt(252) * 100.0)


def tag_events_with_vol(
    events: pd.DataFrame,
    event_date_col: str = "event_date",
    vix_ticker: str = "^VIX",
    move_ticker: str = "^MOVE",
    spy_prices: Optional[pd.DataFrame] = None,
    tlt_prices: Optional[pd.DataFrame] = None,
    lookback_days: int = 252,
) -> pd.DataFrame:
    """
    Attach pre-event VIX/MOVE (T−1 last close before event) and simple post-event
    realized vol on SPY/TLT windows (requires price frames with ``date``, ``close``).
    """
    ev = events.copy()
    ev[event_date_col] = pd.to_datetime(ev[event_date_col]).dt.normalize()

    vix = storage.query_vol_index(vix_ticker, days=lookback_days * 3)
    move = storage.query_vol_index(move_ticker, days=lookback_days * 3)

    def _pre_iv(vol_df: pd.DataFrame, e: pd.Timestamp) -> float:
        if vol_df is None or vol_df.empty:
            return float("nan")
        d = vol_df[vol_df["date"] < e]
        if d.empty:
            return float("nan")
        return float(d.iloc[-1]["close"])

    pre_vix, pre_move = [], []
    rv_spy_0_5, rv_tlt_0_5 = [], []
    for _, row in ev.iterrows():
        e = row[event_date_col]
        pre_vix.append(_pre_iv(vix, e))
        pre_move.append(_pre_iv(move, e))
        if spy_prices is not None:
            rv_spy_0_5.append(realized_vol_over_window(spy_prices, e, 0, 5))
        else:
            rv_spy_0_5.append(float("nan"))
        if tlt_prices is not None:
            rv_tlt_0_5.append(realized_vol_over_window(tlt_prices, e, 0, 5))
        else:
            rv_tlt_0_5.append(float("nan"))

    out = ev.copy()
    out["vix_pre"] = pre_vix
    out["move_pre"] = pre_move
    out["rv_spy_h0_h5_ann"] = rv_spy_0_5
    out["rv_tlt_h0_h5_ann"] = rv_tlt_0_5
    out["vol_miss_spy"] = np.array(rv_spy_0_5) - np.array(pre_vix)
    return out


def merge_prices_for_iv_rv(
    spy: pd.DataFrame,
    tlt: Optional[pd.DataFrame] = None,
    window: int = 20,
) -> tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """Return SPY (and optionally TLT) frames with ``rv_pct`` column."""
    s = realized_volatility(spy, window_days=window)
    if tlt is None:
        return s, None
    t = realized_volatility(tlt, window_days=window)
    return s, t
