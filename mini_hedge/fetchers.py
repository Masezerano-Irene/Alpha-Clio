"""Fetch economic data from FRED and BLS APIs, return as DataFrames, auto-store."""

import json
import logging
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional
from dateutil.relativedelta import relativedelta

import pandas as pd

from mini_hedge import config
from mini_hedge import storage

_log = logging.getLogger(__name__)

# BLS "timeseries/data" only returns a limited calendar-year span per request (commonly ~10y).
# Longer windows require multiple requests; see https://www.bls.gov/developers/
_MAX_BLS_CALENDAR_YEARS_PER_REQUEST = 10
_FRED_PAGE_LIMIT = 100_000


def _fred_request(params):
    """GET FRED series/observations; params is a dict of query string keys/values."""
    q = urllib.parse.urlencode(params)
    url = f"{config.FRED_BASE}?{q}"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def _bls_year_ranges(start_year: int, end_year: int, max_span: int):
    """Inclusive (lo, hi) year pairs from start_year..end_year, each covering at most max_span years."""
    ranges = []
    hi = end_year
    while hi >= start_year:
        lo = max(start_year, hi - max_span + 1)
        ranges.append((lo, hi))
        hi = lo - 1
    ranges.reverse()
    return ranges


def _parse_bls_json_to_rows(data):
    """Turn one BLS JSON response into list of row dicts (date, value, footnotes)."""
    if data["status"] != "REQUEST_SUCCEEDED":
        msg = data.get("message", data["status"])
        raise RuntimeError(f"BLS error: {msg}")

    results = []
    for series in data["Results"]["series"]:
        for item in series["data"]:
            if item["value"] == "-":
                continue
            period = item["period"].replace("M", "").zfill(2)
            footnote_texts = [
                f["text"] for f in item.get("footnotes", [])
                if f and f.get("text")
            ]
            results.append({
                "date": f"{item['year']}-{period}-01",
                "value": item["value"],
                "footnotes": "; ".join(footnote_texts),
            })
    return results


def fetch_fred(series_id, fetch_months=None):
    """Fetch observations from FRED. Returns a DataFrame and stores in SQLite.

    ``fetch_months=None`` uses config: full history when FETCH_FULL_HISTORY else
    DEFAULT_FETCH_MONTHS. Pass an int to always limit the API window to that many months.

    Columns: date (datetime64), value (float64), series_id (str)
    """
    if not config.FRED_API_KEY:
        raise ValueError(
            "FRED_API_KEY is not set. Get a free key at https://fred.stlouisfed.org"
        )

    use_full = fetch_months is None and config.FETCH_FULL_HISTORY
    if fetch_months is None and not config.FETCH_FULL_HISTORY:
        fetch_months = config.DEFAULT_FETCH_MONTHS

    if use_full:
        # Paginate: FRED caps at _FRED_PAGE_LIMIT observations per call.
        all_obs = []
        offset = 0
        while True:
            data = _fred_request({
                "series_id": series_id,
                "api_key": config.FRED_API_KEY,
                "file_type": "json",
                "sort_order": "asc",
                "limit": str(_FRED_PAGE_LIMIT),
                "offset": str(offset),
            })
            batch = data.get("observations") or []
            all_obs.extend(batch)
            if len(batch) < _FRED_PAGE_LIMIT:
                break
            offset += _FRED_PAGE_LIMIT
        obs_raw = all_obs
    else:
        start = (datetime.today() - relativedelta(months=fetch_months)).strftime("%Y-%m-%d")
        data = _fred_request({
            "series_id": series_id,
            "api_key": config.FRED_API_KEY,
            "file_type": "json",
            "observation_start": start,
            "sort_order": "desc",
            "limit": str(_FRED_PAGE_LIMIT),
        })
        obs_raw = data["observations"]

    # Filter out missing values (FRED uses '.' for missing)
    obs = [o for o in obs_raw if o["value"] != "."]
    if not obs:
        df = pd.DataFrame(columns=["date", "value"])
    else:
        df = pd.DataFrame(obs)[["date", "value"]]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = df["value"].astype(float)
    df["series_id"] = series_id
    df = df.sort_values("date", ascending=False).drop_duplicates(subset=["date"]).reset_index(
        drop=True
    )

    # Persist to SQLite
    storage.upsert_observations(df, source="fred")

    return df


def fetch_bls(series_id, fetch_months=None):
    """Fetch observations from BLS. Returns a DataFrame and stores in SQLite.

    ``fetch_months=None`` uses config: from BLS_FULL_HISTORY_START_YEAR when
    FETCH_FULL_HISTORY else DEFAULT_FETCH_MONTHS. Pass an int to limit the window.

    Columns: date (datetime64), value (float64), series_id (str), footnotes (str)
    """
    if not config.BLS_API_KEY:
        raise ValueError(
            "BLS_API_KEY is not set. Get a free key at https://www.bls.gov/developers/"
        )

    today = datetime.today()
    use_full = fetch_months is None and config.FETCH_FULL_HISTORY
    if use_full:
        year_lo, year_hi = config.BLS_FULL_HISTORY_START_YEAR, today.year
    else:
        if fetch_months is None:
            fetch_months = config.DEFAULT_FETCH_MONTHS
        start = today - relativedelta(months=fetch_months)
        year_lo, year_hi = start.year, today.year
    year_ranges = _bls_year_ranges(
        year_lo, year_hi, _MAX_BLS_CALENDAR_YEARS_PER_REQUEST
    )

    results = []
    for y0, y1 in year_ranges:
        payload = {
            "seriesid": [series_id],
            "startyear": str(y0),
            "endyear": str(y1),
            "registrationkey": config.BLS_API_KEY,
        }

        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            config.BLS_BASE, data=body, headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())

        results.extend(_parse_bls_json_to_rows(data))

    df = pd.DataFrame(results)
    df = df.drop_duplicates(subset=["date"], keep="last")
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = df["value"].astype(float)
    df["series_id"] = series_id
    df = df.sort_values("date", ascending=False).reset_index(drop=True)

    # Persist to SQLite
    storage.upsert_observations(df, source="bls")

    return df


# ── Cleveland Fed Inflation Nowcast ───────────────────────────────────────────

# The Cleveland Fed publishes a monthly CPI nowcast (MoM and YoY point forecasts)
# before the official BLS release. This is free, updated continuously, and
# more accurate than the EMA approximation.
#
# Data page: https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting
_CLEVELAND_FED_URL = (
    "https://www.clevelandfed.org"
    "/~/media/Files/indicators-and-data/inflation-nowcasting"
    "/CPI_central_tendency_data.csv"
)


def fetch_cleveland_fed(save_csv: bool = True, csv_path=None) -> pd.DataFrame:
    """Fetch CPI consensus forecasts from the Cleveland Fed Inflation Nowcasting page.

    The Cleveland Fed model produces a rolling MoM CPI forecast that is updated
    daily as new macro data arrives. It is one of the best freely available
    proxies for 'what the market expects' before a CPI release.

    Parameters
    ----------
    save_csv : bool
        If True (default), merges results into data/cpi_consensus.csv so that
        compute_surprises(method='real') picks them up automatically.
    csv_path : str or Path, optional
        Override the default CSV save location.

    Returns DataFrame with columns:
        date           — BLS release date (nearest release date for each forecast)
        consensus_mom  — MoM% CPI forecast from the Cleveland Fed model
    """
    import csv as csv_mod
    import io

    path = csv_path or (config.PROJECT_ROOT / "data" / "cpi_consensus.csv")

    try:
        req = urllib.request.Request(
            _CLEVELAND_FED_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Mini-Hedge/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8-sig")  # strip BOM if present
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach Cleveland Fed URL:\n  {_CLEVELAND_FED_URL}\n\n"
            "The URL may have changed. Check:\n"
            "  https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting\n"
            f"Original error: {exc}"
        ) from exc

    df_raw = pd.read_csv(io.StringIO(raw))

    # Normalise column names (Cleveland Fed formatting varies by release)
    df_raw.columns = [c.strip().lower().replace(" ", "_") for c in df_raw.columns]

    # Find the date column (may be labelled 'date', 'release_date', 'month', etc.)
    date_col = next(
        (c for c in df_raw.columns if "date" in c or c == "month"), None
    )
    if date_col is None:
        raise ValueError(
            f"Could not find a date column in Cleveland Fed CSV. "
            f"Columns found: {list(df_raw.columns)}"
        )

    # Find MoM CPI column (may be 'cpi_mom', 'mom', 'cpi_month', 'point_forecast', etc.)
    mom_col = next(
        (c for c in df_raw.columns
         if "mom" in c or ("cpi" in c and "yoy" not in c and "year" not in c)),
        None,
    )
    if mom_col is None:
        raise ValueError(
            f"Could not find a MoM CPI column in Cleveland Fed CSV. "
            f"Columns found: {list(df_raw.columns)}\n"
            "Please open the CSV and pass the column name manually."
        )

    df = pd.DataFrame({
        "date": pd.to_datetime(df_raw[date_col]),
        "consensus_mom": pd.to_numeric(df_raw[mom_col], errors="coerce"),
    }).dropna().sort_values("date").reset_index(drop=True)

    if save_csv:
        out_path = Path(path)
        if not out_path.is_absolute():
            out_path = config.PROJECT_ROOT / out_path
        if out_path.exists():
            existing = pd.read_csv(out_path)
            # Accept release_date as alias
            if "release_date" in existing.columns and "date" not in existing.columns:
                existing = existing.rename(columns={"release_date": "date"})
            existing["date"] = pd.to_datetime(existing["date"])
            merged = (
                pd.concat([existing, df], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date", ascending=False)
                .reset_index(drop=True)
            )
        else:
            merged = df.sort_values("date", ascending=False).reset_index(drop=True)
        merged.to_csv(out_path, index=False)
        print(f"Saved {len(merged)} rows to {out_path}")

    return df


# ── Path 3 — Volatility indices (VIX, MOVE) ─────────────────────────────────

_VOL_YF_ALIASES = {
    "VIX": "^VIX",
    "^VIX": "^VIX",
    "MOVE": "^MOVE",
    "^MOVE": "^MOVE",
}
_FRED_VIX_SERIES = "VIXCLS"  # CBOE VIX — daily, close; fallback when yfinance fails


def _normalize_vol_ticker(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    if t in _VOL_YF_ALIASES:
        return _VOL_YF_ALIASES[t]
    if not t.startswith("^"):
        return f"^{t}" if len(t) <= 5 else t.strip()
    return ticker.strip()


def _yf_history_close(yf_ticker: str, start: str, end=None) -> pd.DataFrame:
    """Download daily closes via yfinance; returns date, close, ticker (yf_ticker)."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "yfinance is required for fetch_vol_index. "
            "Install: pip install yfinance"
        ) from exc

    raw = yf.download(
        yf_ticker,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "close", "ticker"])
    raw = raw.reset_index()
    raw.columns = [
        c[0].lower() if isinstance(c, tuple) else str(c).lower()
        for c in raw.columns
    ]
    if "date" not in raw.columns:
        raw = raw.rename(columns={raw.columns[0]: "date"})
    out = pd.DataFrame({
        "date": pd.to_datetime(raw["date"]),
        "close": pd.to_numeric(raw["close"], errors="coerce"),
        "ticker": yf_ticker,
    }).dropna(subset=["close"])
    return out


def fetch_vol_index(
    ticker: str,
    start: Optional[str] = None,
    end=None,
    store: bool = True,
    max_retries: int = 3,
) -> pd.DataFrame:
    """Download a volatility index (e.g. ^VIX, ^MOVE), optionally persist to ``vol_indices``.

    Uses yfinance with exponential backoff retries. If ^VIX fails, falls back to
    FRED ``VIXCLS`` (same index, different vendor) and still stores under ticker ``^VIX``.

    Parameters
    ----------
    ticker : str
        ``VIX``, ``^VIX``, ``MOVE``, or ``^MOVE``.
    start : str, optional
        YYYY-MM-DD lower bound. Default: wide history from config-style default.
    end : str or None
        Exclusive end date for yfinance, optional.
    store : bool
        When True (default), upsert into SQLite ``vol_indices``.
    max_retries : int
        Network / empty-response retries before FRED fallback (VIX only).

    Returns
    -------
    DataFrame with columns: date, close, ticker
    """
    yf_ticker = _normalize_vol_ticker(ticker)
    if start is None:
        start = "1990-01-02" if yf_ticker == "^VIX" else "1988-01-04"

    last_err = None
    df = pd.DataFrame(columns=["date", "close", "ticker"])
    for attempt in range(1, max_retries + 1):
        try:
            df = _yf_history_close(yf_ticker, start=start, end=end)
            if not df.empty:
                break
            raise RuntimeError("yfinance returned no rows")
        except Exception as exc:
            last_err = exc
            _log.warning("fetch_vol_index %s attempt %s/%s: %s", yf_ticker, attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    if df.empty and yf_ticker == "^VIX":
        _log.warning("VIX yfinance failed (%s); using FRED %s", last_err, _FRED_VIX_SERIES)
        fred_df = fetch_fred(_FRED_VIX_SERIES)
        df = pd.DataFrame({
            "date": pd.to_datetime(fred_df["date"]),
            "close": fred_df["value"].astype(float),
            "ticker": "^VIX",
        }).sort_values("date")

    if df.empty:
        raise RuntimeError(
            f"No data for volatility ticker {yf_ticker}. Last error: {last_err}"
        )

    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    if store:
        storage.upsert_vol_indices(df[["ticker", "date", "close"]])

    return df
