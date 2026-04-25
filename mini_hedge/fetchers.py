"""Fetch economic data from FRED and BLS APIs, return as DataFrames, auto-store."""

import json
import logging
import re
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


def fetch_fred_alfred_first_release_dates(
    series_id: str,
    observation_start: str = "1900-01-01",
) -> pd.DataFrame:
    """
    Fetch first-release dates (ALFRED realtime_start) for each observation date.

    This uses the standard FRED observations endpoint with ``realtime_start`` /
    ``realtime_end`` set wide open, which returns one row per vintage per observation.

    Returns DataFrame:
      - date (observation date; month-start for PAYEMS)
      - first_release_date (earliest realtime_start for that observation date)
    """
    data = _fred_request(
        {
            "series_id": series_id,
            "api_key": config.FRED_API_KEY,
            "file_type": "json",
            "sort_order": "asc",
            "observation_start": observation_start,
            "realtime_start": "1776-07-04",
            "realtime_end": "9999-12-31",
            "limit": str(_FRED_PAGE_LIMIT),
        }
    )
    obs = data.get("observations") or []
    if not obs:
        return pd.DataFrame(columns=["date", "first_release_date"])

    df = pd.DataFrame(obs)
    # Filter out missing values (FRED uses '.' for missing)
    df = df[df["value"] != "."].copy()
    if df.empty:
        return pd.DataFrame(columns=["date", "first_release_date"])

    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["realtime_start"] = pd.to_datetime(df["realtime_start"]).dt.normalize()

    out = (
        df.groupby("date", as_index=False)["realtime_start"]
        .min()
        .rename(columns={"realtime_start": "first_release_date"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    return out


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


# ── Phase 4 — Consensus fetchers (public sources) ─────────────────────────────

_INVESTING_NFP_URL = "https://www.investing.com/economic-calendar/nonfarm-payrolls-227"
_RATEPROB_FED_URL = "https://rateprobability.com/fed"
_ATL_MPT_HIST_XLSX_URL = "https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/cenfis/market-probability-tracker/mpt_histdata.xlsx"

_FOMC_PROB_HISTORY_CSV = config.PROJECT_ROOT / "data" / "fomc_probabilities_history.csv"
_FOMC_CONS_HISTORY_CSV = config.PROJECT_ROOT / "data" / "fomc_consensus_history.csv"


def _merge_fomc_history(df: pd.DataFrame, hist_path: Path) -> pd.DataFrame:
    """Prepend vendor/historical rows (authoritative) ahead of scraped forward rows."""
    if not hist_path.exists():
        return df
    h = pd.read_csv(hist_path)
    if "release_date" in h.columns and "date" not in h.columns:
        h = h.rename(columns={"release_date": "date"})
    if "date" not in h.columns:
        return df
    h["date"] = pd.to_datetime(h["date"]).dt.normalize()
    out = pd.concat([h, df], ignore_index=True)
    # Historical rows win on overlap (they appear first).
    out = out.drop_duplicates(subset=["date"], keep="first").sort_values("date").reset_index(drop=True)
    return out


_NFP_RELEASE_HIST = config.PROJECT_ROOT / "data" / "nfp_release_calendar_history.csv"


def _merge_nfp_release_history(df: pd.DataFrame) -> pd.DataFrame:
    """Prepend vendor/historical NFP release calendar rows ahead of scraped rows."""
    if not _NFP_RELEASE_HIST.exists():
        return df
    h = pd.read_csv(_NFP_RELEASE_HIST)
    if "release_date" in h.columns and "event_date" not in h.columns:
        h = h.rename(columns={"release_date": "event_date"})
    h["date"] = pd.to_datetime(h["date"]).dt.normalize()
    h["event_date"] = pd.to_datetime(h["event_date"]).dt.normalize()
    out = pd.concat([h[["date", "event_date"]], df], ignore_index=True)
    return out.drop_duplicates(subset=["date"], keep="first").sort_values("date").reset_index(drop=True)


def _investing_nfp_history_rows(html: str) -> pd.DataFrame:
    """
    Parse the Investing.com NFP history table into rows.

    Returns columns:
      - payroll_month (month-start)
      - release_date
      - forecast_k (may be NaN for future rows)
    """
    rows: list[dict] = []

    # Pull the first big tbody block after the "Release date" header.
    i = html.find("Release date")
    if i == -1:
        return pd.DataFrame(columns=["payroll_month", "release_date", "forecast_k"])

    # Investing pages can be very large; don't truncate early or you'll miss older rows.
    sub = html[i : i + 2_000_000]
    for m in re.finditer(
        r"<tr class=\"relative h-\[37px\][^>]*>[\s\S]*?</tr>",
        sub,
    ):
        tr = m.group(0)
        m_cell = re.search(
            r">([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s*\(([A-Za-z]{3})\)<",
            tr,
        )
        if not m_cell:
            continue
        release_dt = pd.to_datetime(m_cell.group(1), errors="coerce")
        month_abbr = m_cell.group(2)
        if pd.isna(release_dt):
            continue
        try:
            month_num = pd.to_datetime(month_abbr, format="%b").month
        except Exception:
            continue
        year = int(release_dt.year)
        if month_num == 12 and release_dt.month == 1:
            year -= 1
        payroll_month = pd.Timestamp(year=year, month=month_num, day=1).normalize()

        # Extract K-sized numbers in row order (Actual / Forecast / Previous).
        # Forecast is usually the *second* K token when Actual exists; if Actual is blank,
        # Forecast is often the *first* K token.
        ks = [float(x) for x in re.findall(r">([-\d.]+)K<", tr)]
        forecast_k = float("nan")
        if len(ks) >= 2:
            forecast_k = ks[1]
        elif len(ks) == 1:
            forecast_k = ks[0]

        rows.append(
            {
                "payroll_month": payroll_month,
                "release_date": release_dt.normalize(),
                "forecast_k": forecast_k,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return (
        df.dropna(subset=["payroll_month", "release_date"])
        .sort_values(["payroll_month", "release_date"])
        .drop_duplicates(subset=["payroll_month"], keep="last")
        .sort_values("payroll_month")
        .reset_index(drop=True)
    )


def fetch_investing_nfp_forecasts(
    save_csv: bool = True,
    csv_path: str | Path | None = None,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """
    Fetch NFP (Nonfarm Payrolls) consensus *forecast* history from Investing.com.

    This is used for Phase 4 "real" NFP consensus in ``compute_nfp_surprises(method="real")``.

    Output schema matches ``load_nfp_consensus_csv``:
      - date (month-start of the payroll month, e.g. 2026-03-01)
      - consensus_nfp_k (headline forecast in thousands, e.g. 65)
    """
    path = Path(csv_path) if csv_path is not None else (config.PROJECT_ROOT / "data" / "nfp_consensus.csv")
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path

    req = urllib.request.Request(
        _INVESTING_NFP_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; Mini-Hedge/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        raise RuntimeError(
            f"Could not fetch Investing.com NFP page:\n  {_INVESTING_NFP_URL}\n"
            f"Original error: {exc}"
        ) from exc

    hist = _investing_nfp_history_rows(html)
    if hist.empty or hist["forecast_k"].notna().sum() == 0:
        raise RuntimeError(
            "Parsed 0 forecast rows from Investing.com.\n"
            "The site markup likely changed. Update _investing_nfp_history_rows()."
        )

    df = (
        hist.dropna(subset=["forecast_k"])
        .rename(columns={"payroll_month": "date", "forecast_k": "consensus_nfp_k"})
        .assign(consensus_nfp_k=lambda d: d["consensus_nfp_k"].astype(float).round().astype(int))
        [["date", "consensus_nfp_k"]]
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    if max_rows is not None and int(max_rows) > 0 and len(df) > int(max_rows):
        df = df.tail(int(max_rows)).reset_index(drop=True)

    if save_csv:
        if path.exists():
            existing = pd.read_csv(path)
            if "release_date" in existing.columns and "date" not in existing.columns:
                existing = existing.rename(columns={"release_date": "date"})
            existing["date"] = pd.to_datetime(existing["date"]).dt.normalize()
            merged = (
                pd.concat([existing, df], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
                .reset_index(drop=True)
            )
        else:
            merged = df
        merged.to_csv(path, index=False)
        print(f"Saved {len(merged)} rows to {path}")

    return df


def fetch_investing_nfp_release_calendar(
    save_csv: bool = True,
    csv_path: str | Path | None = None,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """
    Build an NFP event calendar from Investing.com: payroll month -> release date.

    Output schema:
      - date        : month-start for the payroll month (YYYY-MM-01)
      - event_date  : release date (YYYY-MM-DD)

    This is used to map NFP surprises (which live on payroll month) to an event day
    suitable for market reaction / forward return calculations.
    """
    path = Path(csv_path) if csv_path is not None else (config.PROJECT_ROOT / "data" / "nfp_release_calendar.csv")
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path

    req = urllib.request.Request(
        _INVESTING_NFP_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; Mini-Hedge/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        raise RuntimeError(
            f"Could not fetch Investing.com NFP page:\n  {_INVESTING_NFP_URL}\n"
            f"Original error: {exc}"
        ) from exc

    hist = _investing_nfp_history_rows(html)
    df = hist.rename(columns={"payroll_month": "date", "release_date": "event_date"})[
        ["date", "event_date"]
    ].copy()
    if df.empty:
        raise RuntimeError(
            "Parsed 0 NFP calendar rows from Investing.com.\n"
            "The site markup likely changed. Update fetch_investing_nfp_release_calendar() parser."
        )

    if max_rows is not None and int(max_rows) > 0 and len(df) > int(max_rows):
        df = df.tail(int(max_rows)).reset_index(drop=True)

    df = _merge_nfp_release_history(df)

    if save_csv:
        if path.exists():
            existing = pd.read_csv(path)
            existing["date"] = pd.to_datetime(existing["date"]).dt.normalize()
            existing["event_date"] = pd.to_datetime(existing["event_date"]).dt.normalize()
            merged = (
                pd.concat([existing, df], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
                .reset_index(drop=True)
            )
        else:
            merged = df
        merged.to_csv(path, index=False)
        print(f"Saved {len(merged)} rows to {path}")

    return df


def fetch_alfred_nfp_release_calendar_history(
    save_csv: bool = True,
    csv_path: str | Path | None = None,
) -> pd.DataFrame:
    """
    Build a long-history NFP release calendar using ALFRED vintages for PAYEMS.

    Output schema matches nfp_release_calendar_history.csv:
      - date       : payroll month-start (PAYEMS observation date)
      - event_date : first release date (ALFRED realtime_start)
    """
    if not config.FRED_API_KEY:
        raise ValueError("FRED_API_KEY is required to query ALFRED vintages.")

    out_path = Path(csv_path) if csv_path is not None else (config.PROJECT_ROOT / "data" / "nfp_release_calendar_history.csv")
    if not out_path.is_absolute():
        out_path = config.PROJECT_ROOT / out_path

    rel = fetch_fred_alfred_first_release_dates("PAYEMS", observation_start="1939-01-01")
    rel = rel.rename(columns={"first_release_date": "event_date"})

    if save_csv:
        if out_path.exists():
            existing = pd.read_csv(out_path)
            existing["date"] = pd.to_datetime(existing["date"]).dt.normalize()
            existing["event_date"] = pd.to_datetime(existing["event_date"]).dt.normalize()
            merged = (
                pd.concat([existing, rel], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
                .reset_index(drop=True)
            )
        else:
            merged = rel
        merged.to_csv(out_path, index=False)
        print(f"Saved {len(merged)} rows to {out_path}")

    return rel


def fetch_atlanta_fed_mpt_histdata_xlsx(
    save_path: str | Path = "data/mpt_histdata.xlsx",
) -> Path:
    """Download Atlanta Fed MPT historical data workbook to disk."""
    p = Path(save_path)
    if not p.is_absolute():
        p = config.PROJECT_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(_ATL_MPT_HIST_XLSX_URL, p)
    return p


def build_fomc_probabilities_history_from_atlanta_mpt(
    xlsx_path: str | Path = "data/mpt_histdata.xlsx",
    save_csv: bool = True,
    csv_path: str | Path | None = None,
) -> pd.DataFrame:
    """
    Convert Atlanta Fed MPT histdata.xlsx into `fomc_probabilities_history.csv`.

    For each FOMC meeting (`reference_start`), we take the last available workbook
    ``date`` strictly before the meeting and read the implied target level.

    Prefer Atlanta Fed's published ``Rate: mean`` (matches their summary stats). If it
    is missing, fall back to reconstructing a weighted mean from the
    ``Prob: <lo>bps - <hi>bps`` rows (can disagree slightly from ``Rate: mean``).

    Then we translate that implied level into an expected change vs the current target
    upper bound on that as-of date using ``DFEDTARU`` from your local SQLite DB.
    """
    p = Path(xlsx_path)
    if not p.is_absolute():
        p = config.PROJECT_ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"Missing MPT workbook: {p}. Download it first.")

    df = pd.read_excel(p, sheet_name="DATA")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["reference_start"] = pd.to_datetime(df["reference_start"]).dt.normalize()

    mean = df[df["field"].astype(str) == "Rate: mean"].copy()
    mean["expected_rate_units"] = pd.to_numeric(mean["value"], errors="coerce")
    mean = mean.dropna(subset=["expected_rate_units", "date", "reference_start"])
    mean_before = mean[mean["date"] < mean["reference_start"]].copy()
    mean_last = (
        mean_before.sort_values(["reference_start", "date"])
        .groupby("reference_start", as_index=False)
        .tail(1)
        .rename(columns={"reference_start": "meeting_date", "date": "asof"})[
            ["meeting_date", "asof", "expected_rate_units"]
        ]
        if not mean_before.empty
        else pd.DataFrame(columns=["meeting_date", "asof", "expected_rate_units"])
    )

    prob = df[df["field"].astype(str).str.match(r"^Prob:\s*\d+bps\s*-\s*\d+bps$")].copy()
    prob["p"] = pd.to_numeric(prob["value"], errors="coerce") / 100.0
    mid = prob["target_range"].astype(str).str.extract(r"(?P<lo>\d+)bps\s*-\s*(?P<hi>\d+)bps")
    prob["lo"] = pd.to_numeric(mid["lo"], errors="coerce")
    prob["hi"] = pd.to_numeric(mid["hi"], errors="coerce")
    prob["mid_bps"] = (prob["lo"] + prob["hi"]) / 2.0
    prob = prob.dropna(subset=["p", "mid_bps", "date", "reference_start"])
    prob["w"] = prob["p"] * prob["mid_bps"]
    exp = (
        prob.groupby(["date", "reference_start"], as_index=False)["w"]
        .sum()
        .rename(columns={"w": "expected_rate_units"})
        .sort_values(["reference_start", "date"])
        .reset_index(drop=True)
    )
    exp["date"] = pd.to_datetime(exp["date"]).dt.normalize()
    exp["reference_start"] = pd.to_datetime(exp["reference_start"]).dt.normalize()
    before = exp[exp["date"] < exp["reference_start"]].copy()
    prob_last = (
        before.sort_values(["reference_start", "date"])
        .groupby("reference_start", as_index=False)
        .tail(1)
        .rename(columns={"reference_start": "meeting_date", "date": "asof"})[
            ["meeting_date", "asof", "expected_rate_units"]
        ]
        if not before.empty
        else pd.DataFrame(columns=["meeting_date", "asof", "expected_rate_units"])
    )

    if mean_last.empty and prob_last.empty:
        raise RuntimeError("No pre-meeting observations found in MPT histdata workbook.")
    if mean_last.empty:
        last = prob_last
    elif prob_last.empty:
        last = mean_last
    else:
        merged = mean_last.merge(prob_last, on="meeting_date", how="outer", suffixes=("_mean", "_prob"))
        merged["asof"] = merged["asof_mean"].combine_first(merged["asof_prob"])
        merged["expected_rate_units"] = merged["expected_rate_units_mean"].combine_first(
            merged["expected_rate_units_prob"]
        )
        last = merged[["meeting_date", "asof", "expected_rate_units"]]

    out = last.sort_values("meeting_date").reset_index(drop=True)

    # Map expected rate to expected change vs current target upper bound at as-of.
    ff = storage.query_series("DFEDTARU").copy()
    ff["date"] = pd.to_datetime(ff["date"]).dt.normalize()
    ff = ff.rename(columns={"value": "ff_upper_pct"})[["date", "ff_upper_pct"]].sort_values("date")
    out = out.merge(ff, left_on="asof", right_on="date", how="left", suffixes=("", "_ff"))
    out = out.rename(columns={"meeting_date": "date"})
    # Atlanta Fed MPT implied levels are on a 0–100 scale; convert to percent points via /100.
    # This matches `DFEDTARU` (FRED) which is expressed in percent (e.g. 5.25).
    out["expected_rate_pct"] = out["expected_rate_units"] / 100.0
    out["expected_change_pp"] = out["expected_rate_pct"] - out["ff_upper_pct"]

    # Keep only what the rest of the pipeline needs.
    res = out.rename(columns={"meeting_date": "date"})[["date", "expected_change_pp"]].copy()
    res["date"] = pd.to_datetime(res["date"]).dt.normalize()
    res = res.dropna(subset=["expected_change_pp"]).sort_values("date").reset_index(drop=True)

    out_path = Path(csv_path) if csv_path is not None else (config.PROJECT_ROOT / "data" / "fomc_probabilities_history.csv")
    if not out_path.is_absolute():
        out_path = config.PROJECT_ROOT / out_path
    if save_csv:
        if out_path.exists():
            existing = pd.read_csv(out_path)
            if "release_date" in existing.columns and "date" not in existing.columns:
                existing = existing.rename(columns={"release_date": "date"})
            existing["date"] = pd.to_datetime(existing["date"]).dt.normalize()
            merged = (
                pd.concat([existing, res], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
                .reset_index(drop=True)
            )
        else:
            merged = res
        merged.to_csv(out_path, index=False)
        print(f"Saved {len(merged)} rows to {out_path}")

    return res


def fetch_rateprobability_fomc_consensus(
    save_csv: bool = True,
    csv_path: str | Path | None = None,
    max_rows: int = 20,
) -> pd.DataFrame:
    """
    Fetch a simple market-implied FOMC consensus change series from rateprobability.com.

    Writes ``data/fomc_consensus.csv`` with:
      - date (meeting date)
      - consensus_change_pp (expected change in target upper bound, in percentage points)

    Note: This is a pragmatic approximation. For a fully "official" FedWatch feed,
    CME provides a paid OAuth API.
    """
    path = Path(csv_path) if csv_path is not None else (config.PROJECT_ROOT / "data" / "fomc_consensus.csv")
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path

    req = urllib.request.Request(
        _RATEPROB_FED_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Mini-Hedge/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        raise RuntimeError(
            f"Could not fetch rateprobability.com page:\n  {_RATEPROB_FED_URL}\n"
            f"Original error: {exc}"
        ) from exc

    # Parse SSR snapshot table rows:
    # <td ... data-col="meeting">Apr 29, 2026</td> ... <td ... data-col="delta">-21.0</td>
    matches = list(
        re.finditer(
            r'data-col="meeting">([^<]+)</td>[\s\S]{0,600}?data-col="delta">([-\d.]+)</td>',
            html,
        )
    )
    if not matches:
        raise RuntimeError(
            "Parsed 0 meeting rows from rateprobability.com.\n"
            "The site markup likely changed. Update fetch_rateprobability_fomc_consensus() regex."
        )

    # Build expected change per meeting by differencing the cumulative Δ vs current (bps).
    rows = []
    last_cum_bps = 0.0
    for m in matches[: max_rows or None]:
        meeting_dt = pd.to_datetime(m.group(1).strip(), errors="coerce")
        if pd.isna(meeting_dt):
            continue

        cum_bps = float(m.group(2))
        inc_bps = cum_bps - last_cum_bps
        last_cum_bps = cum_bps

        # Map to nearest 25bp step because target changes come in 25bp increments.
        inc_pp = round(inc_bps / 100.0, 4)
        inc_pp_25 = round(round(inc_pp / 0.25) * 0.25, 2) if inc_pp == inc_pp else float("nan")

        rows.append(
            {
                "date": meeting_dt.normalize(),
                "consensus_change_pp": inc_pp_25,
            }
        )

    df = pd.DataFrame(rows).dropna(subset=["date"]).drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    if df.empty:
        raise RuntimeError("No usable meeting rows parsed for FOMC consensus.")

    df = _merge_fomc_history(df, _FOMC_CONS_HISTORY_CSV)

    if save_csv:
        if path.exists():
            existing = pd.read_csv(path)
            if "release_date" in existing.columns and "date" not in existing.columns:
                existing = existing.rename(columns={"release_date": "date"})
            existing["date"] = pd.to_datetime(existing["date"]).dt.normalize()
            merged = (
                pd.concat([existing, df], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
                .reset_index(drop=True)
            )
        else:
            merged = df
        merged.to_csv(path, index=False)
        print(f"Saved {len(merged)} rows to {path}")

    return df


def fetch_rateprobability_fomc_probabilities(
    save_csv: bool = True,
    csv_path: str | Path | None = None,
    max_rows: int = 20,
) -> pd.DataFrame:
    """
    Fetch a lightweight "probability" view for FOMC outcomes from rateprobability.com.

    IMPORTANT CAVEAT:
    rateprobability.com exposes a single column "Probability of Hike(Cut)" rather than
    a full FedWatch-style distribution across target ranges. We therefore approximate a
    3-state distribution:
      - p_hold   = 1 - p_change
      - p_cut25  = p_change when Δ vs current is negative
      - p_hike25 = p_change when Δ vs current is positive

    This is intentionally simple, but it makes "expected change" non-zero when the
    market prices *some* chance of a move (useful for "hold but surprise" research).

    Output CSV schema:
      - date (meeting date)
      - p_hold, p_cut25, p_hike25  (0..1)
      - expected_change_pp         (= -0.25*p_cut25 + 0.25*p_hike25)
    """
    path = Path(csv_path) if csv_path is not None else (config.PROJECT_ROOT / "data" / "fomc_probabilities.csv")
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path

    req = urllib.request.Request(
        _RATEPROB_FED_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Mini-Hedge/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        raise RuntimeError(
            f"Could not fetch rateprobability.com page:\n  {_RATEPROB_FED_URL}\n"
            f"Original error: {exc}"
        ) from exc

    # Parse SSR snapshot row fields: meeting date, prob-of-change, delta-vs-current.
    matches = list(
        re.finditer(
            r'data-col="meeting">([^<]+)</td>[\s\S]{0,600}?data-col="prob">\(?([-\d.]+)%\)?</td>[\s\S]{0,600}?data-col="delta">([-\d.]+)</td>',
            html,
        )
    )
    if not matches:
        raise RuntimeError(
            "Parsed 0 probability rows from rateprobability.com.\n"
            "The site markup likely changed. Update fetch_rateprobability_fomc_probabilities() regex."
        )

    rows: list[dict] = []
    for m in matches[: max_rows or None]:
        meeting_dt = pd.to_datetime(m.group(1).strip(), errors="coerce")
        if pd.isna(meeting_dt):
            continue
        p_change = abs(float(m.group(2))) / 100.0
        delta_bps = float(m.group(3))

        p_hold = max(0.0, min(1.0, 1.0 - p_change))
        p_cut25 = p_change if delta_bps < 0 else 0.0
        p_hike25 = p_change if delta_bps > 0 else 0.0

        expected_change_pp = round((-0.25 * p_cut25) + (0.25 * p_hike25), 6)

        rows.append(
            {
                "date": meeting_dt.normalize(),
                "p_hold": round(p_hold, 6),
                "p_cut25": round(p_cut25, 6),
                "p_hike25": round(p_hike25, 6),
                "expected_change_pp": expected_change_pp,
            }
        )

    df = (
        pd.DataFrame(rows)
        .dropna(subset=["date"])
        .drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    if df.empty:
        raise RuntimeError("No usable meeting rows parsed for FOMC probabilities.")

    df = _merge_fomc_history(df, _FOMC_PROB_HISTORY_CSV)

    if save_csv:
        if path.exists():
            existing = pd.read_csv(path)
            if "release_date" in existing.columns and "date" not in existing.columns:
                existing = existing.rename(columns={"release_date": "date"})
            existing["date"] = pd.to_datetime(existing["date"]).dt.normalize()
            merged = (
                pd.concat([existing, df], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
                .reset_index(drop=True)
            )
        else:
            merged = df
        merged.to_csv(path, index=False)
        print(f"Saved {len(merged)} rows to {path}")

    return df
