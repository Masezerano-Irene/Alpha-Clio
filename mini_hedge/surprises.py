"""
Week 2 — Surprise Calculations: surprises.py

THE most important module in Phase 1.

A CPI 'surprise' = Actual release − What the market expected.

Why surprises matter:
  CPI of 0.4% MoM is MEANINGLESS without context.
  If the market expected 0.2%, that 0.4% is a massive hot surprise → bonds fall.
  If the market expected 0.6%, that 0.4% is actually a cool surprise → bonds rally.
  The SAME number produces opposite market reactions depending on the expectation.

THREE consensus methods (choose one):
  1. 'naive'  — Simple rolling average of last 3 months. Equal weight.
                 Fast to compute. Slow to react to regime changes.

  2. 'ema'    — Exponential Moving Average. Recent months weighted more heavily.
                 Faster to adapt. Better when inflation is trending.
                 This is what most practitioner forecasters use as a baseline.

  3. 'real'   — Actual Bloomberg/Reuters economist survey forecasts from CSV.
                 Most accurate. Requires manual data collection from investing.com.
                 Use this for Week 3 final backtest.

The surprise is your core trading signal:
  Surprise > +threshold  → Hot  (hawkish) → Short TLT / Short SPY
  Surprise < -threshold  → Cool (dovish)  → Long  TLT / Long  SPY
  |Surprise| < threshold → No edge        → Stay out
"""

import warnings
import pandas as pd
import numpy as np
from pathlib import Path

from mini_hedge.config import PROJECT_ROOT
from mini_hedge.transforms import enrich_series, load_series


# ── Series IDs ────────────────────────────────────────────────────────────────

CPI_BLS  = "CUUR0000SA0"   # CPI-U, All Urban, Not Seasonally Adjusted (BLS)
CORE_CPI = "CPILFESL"      # Core CPI, Seasonally Adjusted (FRED)
PAYEMS   = "PAYEMS"        # All Employees, Total Nonfarm — monthly level (FRED)
DFEDTARU = "DFEDTARU"      # Fed Funds Target Range — Upper Limit (FRED, daily)


# ── 1. Load CPI MoM ──────────────────────────────────────────────────────────

def get_cpi_mom(seasonally_adjusted: bool = False) -> pd.DataFrame:
    """
    Load CPI and compute Month-over-Month percentage change.

    This is the number that appears in headlines: "CPI rose 0.4% in March."

    Parameters
    ----------
    seasonally_adjusted : bool
        False → CUUR0000SA0 (BLS, not SA) — raw / unadjusted
        True  → CPIAUCSL (FRED, SA) — if you have fetched it

    Returns DataFrame sorted oldest-first.
    Columns: date, value, mom_pct, yoy_pct, zscore
    """
    series_id = CPI_BLS if not seasonally_adjusted else "CPIAUCSL"
    df = enrich_series(series_id)
    df = df[["date", "value", "mom_pct", "yoy_pct", "zscore"]].dropna(subset=["mom_pct"])
    return df.reset_index(drop=True)


# ── 2a. Naive consensus — simple rolling average ──────────────────────────────

def naive_consensus(
    df: pd.DataFrame,
    value_col: str = "mom_pct",
    window: int = 3,
) -> pd.DataFrame:
    """
    Estimate consensus using a simple equally-weighted rolling average.

    Each month in the window contributes the same weight.
    Simple but slow to react when inflation changes direction quickly.

    Example with window=3:
      Month 1 weight: 33%
      Month 2 weight: 33%
      Month 3 weight: 33%

    Columns added:
      consensus_naive   — expected MoM%
      surprise_naive    — actual minus naive consensus
    """
    df = df.copy()
    shifted = df[value_col].shift(1)          # use only info BEFORE this release
    df["consensus_naive"]  = shifted.rolling(window=window, min_periods=1).mean()
    df["surprise_naive"]   = df[value_col] - df["consensus_naive"]
    return df


# ── 2b. EMA consensus — exponential smoothing ────────────────────────────────

def ema_consensus(
    df: pd.DataFrame,
    value_col: str = "mom_pct",
    span: int = 3,
) -> pd.DataFrame:
    """
    Estimate consensus using Exponential Moving Average (EMA).

    EMA gives MORE weight to recent months and LESS weight to older ones.
    The weight decays exponentially backwards in time.

    With span=3, approximate weights are:
      Most recent month:  ~50%
      2 months ago:       ~25%
      3 months ago:       ~12.5%
      4 months ago:        ~6%  ... and so on

    Formula: EMA_t = α × X_{t-1} + (1-α) × EMA_{t-1}
    where α = 2 / (span + 1)   →   span=3 gives α = 0.5

    Why EMA is better than naive for CPI forecasting:
      - CPI trends. When inflation is RISING, recent months matter more.
        A 3-month simple average anchors to old data too long.
      - EMA adapts faster when the trend changes — closer to how
        professional economists update their forecasts in real time.
      - Less lag when regime shifts happen (e.g., 2021 inflation surge).

    Parameters
    ----------
    span : int
        Controls how fast older data decays. Smaller span = faster decay.
        span=3  → half-life ≈ 2 months  (very responsive)
        span=6  → half-life ≈ 4 months  (moderate)
        span=12 → half-life ≈ 8 months  (slow, like a year-long memory)
        Default span=3 is reasonable for monthly CPI data.

    Columns added:
      consensus_ema    — EMA-based expected MoM%
      surprise_ema     — actual minus EMA consensus
    """
    df = df.copy()
    shifted = df[value_col].shift(1)          # use only info BEFORE this release
    df["consensus_ema"]  = shifted.ewm(span=span, adjust=False).mean()
    df["surprise_ema"]   = df[value_col] - df["consensus_ema"]
    return df


# ── 3. Real consensus from CSV ────────────────────────────────────────────────

def _convert_yoy_consensus_to_mom(df: pd.DataFrame) -> pd.DataFrame:
    """Convert YoY% consensus values to MoM% using CPI index levels from storage.

    Formula per row:
        implied_CPI  = CPI_{ref_month - 12m} × (1 + YoY/100)
        consensus_mom = (implied_CPI / CPI_{ref_month - 1m} - 1) × 100

    Falls back to YoY/12 for any month where CPI data is missing.
    """
    from mini_hedge import storage

    cpi_raw = storage.query_series("CUUR0000SA0")
    if cpi_raw.empty:
        import warnings
        warnings.warn(
            "CPI index data not in DB — using YoY/12 approximation for MoM conversion. "
            "Run fetch_bls('CUUR0000SA0') first for accurate results."
        )
        df = df.copy()
        df["consensus_mom"] = (df["consensus_mom"] / 12).round(4)
        return df

    cpi_raw["date"] = pd.to_datetime(cpi_raw["date"])
    cpi_index = cpi_raw.sort_values("date").set_index("date")["value"]

    def _yoy_to_mom(row):
        ref = pd.Timestamp(row.get("ref_month", row["date"]))
        yoy = row["consensus_mom"]
        base = (ref - pd.DateOffset(months=12)).to_period("M").to_timestamp()
        prev = (ref - pd.DateOffset(months=1)).to_period("M").to_timestamp()
        try:
            implied = cpi_index[base] * (1 + yoy / 100)
            return round((implied / cpi_index[prev] - 1) * 100, 4)
        except KeyError:
            return round(yoy / 12, 4)

    df = df.copy()
    df["consensus_mom"] = df.apply(_yoy_to_mom, axis=1)
    return df


def load_consensus_csv(
    filepath: str = "data/cpi_consensus.csv",
    auto_fetch: bool = True,
) -> pd.DataFrame:
    """
    Load real economist consensus forecasts from a CSV file.

    If the file is missing and ``auto_fetch`` is True, tries
    ``fetch_cleveland_fed()`` once to create ``data/cpi_consensus.csv``
    (requires network). Set ``auto_fetch=False`` to require a manual file.

    Accepted column names:
      • date or release_date  — the BLS calendar release date (e.g. 2026-04-10 or "Apr 10, 2026")
      • consensus_mom         — MoM% OR YoY% consensus forecast.
                                Values > 1.5 are treated as YoY% and auto-converted to MoM%.

    How to build this file (free):
      1. Go to https://www.investing.com/economic-calendar/cpi-733
         (that page shows YoY — values like 2.4, 3.1 — which is fine, auto-converted)
      2. Copy Date + Forecast columns into a CSV.
      3. Save as Mini_Hedge/data/cpi_consensus.csv

    Or run fetch_cleveland_fed() which builds this file automatically.

    Optional column `ref_month` (YYYY-MM-01) overrides date alignment.

    Returns DataFrame with columns: date (datetime), consensus_mom (float, MoM%)
    """
    path = Path(filepath)
    if not path.is_absolute():
        path = PROJECT_ROOT / filepath

    if not path.exists() and auto_fetch:
        from mini_hedge.fetchers import fetch_cleveland_fed

        try:
            fetch_cleveland_fed(save_csv=True, csv_path=path)
        except Exception as exc:
            raise FileNotFoundError(
                f"Consensus file not found: {path}\n\n"
                "Tried fetch_cleveland_fed() but it failed:\n"
                f"  {exc}\n\n"
                "Fix network access, or add the file manually from:\n"
                "  https://www.investing.com/economic-calendar/cpi-733\n"
                "Or use method='ema' without real consensus."
            ) from exc

    if not path.exists():
        raise FileNotFoundError(
            f"Consensus file not found: {path}\n\n"
            "Options:\n"
            "  1. Run fetch_cleveland_fed() to build it automatically.\n"
            "  2. Visit https://www.investing.com/economic-calendar/cpi-733\n"
            "     and save Date + Forecast columns as data/cpi_consensus.csv\n\n"
            "Or use method='ema' to proceed without real consensus data."
        )

    df = pd.read_csv(path)

    # Accept 'release_date' as an alias for 'date'
    if "release_date" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"release_date": "date"})

    df["date"] = pd.to_datetime(df["date"])

    missing = [c for c in ["date", "consensus_mom"] if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing columns: {missing}")

    cols = ["date", "consensus_mom"]
    if "ref_month" in df.columns:
        cols.append("ref_month")
    df = df[cols].sort_values("date").reset_index(drop=True)

    # Auto-detect YoY% (investing.com exports YoY by default).
    # MoM CPI is typically 0.0–0.6%. If the mean exceeds 1.5 it is almost
    # certainly YoY% — convert to MoM% using CPI index data from storage.
    if df["consensus_mom"].mean() > 1.5:
        df = _attach_ref_month_for_cpi_merge(df)
        df = _convert_yoy_consensus_to_mom(df)

    return df[["date", "consensus_mom"] + (["ref_month"] if "ref_month" in df.columns else [])].reset_index(drop=True)


def _attach_ref_month_for_cpi_merge(consensus: pd.DataFrame) -> pd.DataFrame:
    """Align consensus rows to CPI `date` (month-start of reference month).

    CSV `date` may be either (a) CPI reference month (YYYY-MM-01) or (b) BLS
    *release* calendar day (~10th–15th). For (b), map to reference month ≈ prior
    calendar month start (US CPI is typically the prior month's print).
    """
    df = consensus.copy()
    df["date"] = pd.to_datetime(df["date"])
    if "ref_month" in df.columns:
        df["ref_month"] = pd.to_datetime(df["ref_month"]).dt.normalize()
        return df
    day1 = df["date"].dt.day == 1
    df["ref_month"] = df["date"].dt.normalize()
    if (~day1).any():
        sub = df.loc[~day1, "date"]
        df.loc[~day1, "ref_month"] = (
            sub - pd.DateOffset(months=1)
        ).dt.to_period("M").dt.to_timestamp()
    return df


# ── 4. Core signal builder ────────────────────────────────────────────────────

def _build_signal(
    cpi: pd.DataFrame,
    consensus_col: str,
    surprise_threshold: float,
) -> pd.DataFrame:
    """Shared logic: compute surprise z-score, direction, and signal."""
    cpi = cpi.copy()
    cpi["consensus_mom"] = cpi[consensus_col]
    cpi["surprise"]      = cpi["mom_pct"] - cpi["consensus_mom"]

    # Z-score of the surprise: how big was this vs historical surprises?
    roll = cpi["surprise"].rolling(window=60, min_periods=12)
    roll_std = roll.std().replace(0, np.nan)
    cpi["surprise_zscore"] = (cpi["surprise"] - roll.mean()) / roll_std

    # Direction (+1 hot, -1 cool, 0 flat)
    cpi["surprise_dir"] = np.sign(cpi["surprise"])

    # Signal — only fire when surprise is large enough to matter
    cpi["signal"] = cpi.apply(
        lambda r: int(r["surprise_dir"]) if abs(r["surprise"]) >= surprise_threshold else 0,
        axis=1,
    )
    return cpi


# ── 5. Master compute function ────────────────────────────────────────────────

def compute_surprises(
    method: str = "ema",
    consensus_csv: str = "data/cpi_consensus.csv",
    surprise_threshold: float = 0.15,
    ema_span: int = 3,
    naive_window: int = 3,
    auto_fetch_consensus: bool = True,
    # Legacy support
    use_naive: bool = None,
) -> pd.DataFrame:
    """
    Build the complete CPI surprise table — the core of your trading signal.

    Parameters
    ----------
    method : str
        'ema'   → Exponential smoothing consensus (DEFAULT — best for trending data)
        'naive' → Simple rolling average consensus (equal weights)
        'real'  → Load real consensus from CSV (most accurate)

    surprise_threshold : float
        Minimum |surprise| in MoM % to generate a trade signal.
        ±0.15% default means small noise is ignored. Tune in Week 3.

    ema_span : int
        EMA decay speed. span=3 → ~50% weight on most recent month.
        Only used when method='ema'.

    naive_window : int
        Number of months for simple rolling average.
        Only used when method='naive'.

    auto_fetch_consensus : bool
        When method='real' and the consensus CSV is missing, try Cleveland Fed
        download once (same as load_consensus_csv(..., auto_fetch=True)).

    Returns DataFrame with columns:
      date             — CPI reference month
      value            — raw CPI index level
      mom_pct          — actual MoM % change (THE number markets trade)
      yoy_pct          — annual inflation rate
      zscore           — z-score of raw CPI level
      consensus_mom    — what was 'expected' (method-dependent)
      surprise         — actual minus consensus  ← YOUR SIGNAL
      surprise_zscore  — how large this surprise was vs history
      surprise_dir     — +1 hot / -1 cool / 0 flat
      signal           — +1 / -1 / 0  (threshold-filtered trade direction)
      core_cpi_mom     — Core CPI MoM for context
    """
    # Legacy: use_naive=True → method='naive', use_naive=False → method='real'
    if use_naive is not None:
        method = "naive" if use_naive else "real"

    cpi = get_cpi_mom()

    if method == "ema":
        cpi = ema_consensus(cpi, value_col="mom_pct", span=ema_span)
        cpi = _build_signal(cpi, "consensus_ema", surprise_threshold)

    elif method == "naive":
        cpi = naive_consensus(cpi, value_col="mom_pct", window=naive_window)
        cpi = _build_signal(cpi, "consensus_naive", surprise_threshold)

    elif method == "real":
        real_cons = load_consensus_csv(consensus_csv, auto_fetch=auto_fetch_consensus)
        real_cons = _attach_ref_month_for_cpi_merge(real_cons)
        cpi = cpi.merge(
            real_cons[["ref_month", "consensus_mom"]],
            left_on="date",
            right_on="ref_month",
            how="left",
        )
        cpi = cpi.drop(columns=["ref_month"], errors="ignore")
        cpi = _build_signal(cpi, "consensus_mom", surprise_threshold)

    else:
        raise ValueError(f"method must be 'ema', 'naive', or 'real'. Got: '{method}'")

    # Add Core CPI for context
    try:
        core = enrich_series(CORE_CPI)[["date", "mom_pct"]].rename(
            columns={"mom_pct": "core_cpi_mom"}
        )
        cpi = cpi.merge(core, on="date", how="left")
    except Exception:
        cpi["core_cpi_mom"] = np.nan

    keep = [
        "date", "value", "mom_pct", "yoy_pct", "zscore",
        "consensus_mom", "surprise", "surprise_zscore",
        "surprise_dir", "signal", "core_cpi_mom",
    ]
    out = cpi[[c for c in keep if c in cpi.columns]].reset_index(drop=True)
    out.attrs["surprise_method"] = method
    return out


# ── 6. Compare methods side by side ──────────────────────────────────────────

def compare_consensus_methods(
    surprise_threshold: float = 0.15,
    ema_span: int = 3,
    naive_window: int = 3,
    consensus_csv: str = "data/cpi_consensus.csv",
    auto_fetch_consensus: bool = False,
    include_real: bool = True,
) -> pd.DataFrame:
    """
    Run naive, EMA, and real (survey CSV) consensus on the same yield events and compare.

    Win rate = share of days where bond direction matched the signal (1-day window),
    same definition for all three. ``real`` can tie out lower than EMA if survey
    forecasts align less often with post-release price action — that is an empirical
    fact, not a bug.

    Returns a summary DataFrame with columns Method, Span/Window, Total signals, etc.

    ``include_real`` — set False when ``data/cpi_consensus.csv`` is not available to avoid
    noisy warnings from the ``real`` branch.
    """
    from mini_hedge.prices import yield_around_releases

    events = yield_around_releases()
    events["release_date"] = pd.to_datetime(events["release_date"])
    events["ym"] = events["release_date"].dt.to_period("M")

    methods = ("naive", "ema", "real") if include_real else ("naive", "ema")
    rows = []
    for method in methods:
        span_label = (
            Path(consensus_csv).name
            if method == "real"
            else (f"span={ema_span}" if method == "ema" else f"window={naive_window}")
        )
        try:
            if method == "real":
                surp = compute_surprises(
                    method="real",
                    surprise_threshold=surprise_threshold,
                    consensus_csv=consensus_csv,
                    auto_fetch_consensus=auto_fetch_consensus,
                )
            else:
                surp = compute_surprises(
                    method=method,
                    surprise_threshold=surprise_threshold,
                    ema_span=ema_span,
                    naive_window=naive_window,
                )
        except Exception as exc:
            warnings.warn(f"compare_consensus_methods: skipping {method!r}: {exc}")
            rows.append({
                "Method":           method.upper(),
                "Span/Window":      span_label,
                "Total signals":    0,
                "Hot (+1)":         0,
                "Cool (-1)":        0,
                "Win rate":         "n/a",
                "Win rate (hot)":   "n/a",
                "Win rate (cool)":  "n/a",
                "Avg |surprise|":   "n/a",
            })
            continue

        surp["ym"] = (surp["date"] + pd.DateOffset(months=1)).dt.to_period("M")

        merged = surp.merge(
            events[["ym", "yield_chg_1d", "price_dir_1d"]], on="ym", how="inner"
        )
        tradeable = merged[
            (merged["signal"] != 0) & merged["yield_chg_1d"].notna()
        ].copy()

        if len(tradeable) == 0:
            warnings.warn(
                f"compare_consensus_methods: {method!r} has no overlapping tradeable events"
            )
            rows.append({
                "Method":           method.upper(),
                "Span/Window":      span_label,
                "Total signals":    0,
                "Hot (+1)":         0,
                "Cool (-1)":        0,
                "Win rate":         "n/a",
                "Win rate (hot)":   "n/a",
                "Win rate (cool)":  "n/a",
                "Avg |surprise|":   "n/a",
            })
            continue

        tradeable["correct"] = tradeable.apply(
            lambda r: 1 if (r["signal"] ==  1 and r["price_dir_1d"] == -1) or
                           (r["signal"] == -1 and r["price_dir_1d"] ==  1) else 0,
            axis=1,
        )

        hot = tradeable[tradeable["signal"] == 1]
        cool = tradeable[tradeable["signal"] == -1]
        n = len(tradeable)

        rows.append({
            "Method":           method.upper(),
            "Span/Window":      span_label,
            "Total signals":    n,
            "Hot (+1)":         len(hot),
            "Cool (-1)":        len(cool),
            "Win rate":         f"{tradeable['correct'].mean() * 100:.1f}%",
            "Win rate (hot)":   f"{hot['correct'].mean() * 100:.1f}%" if len(hot) > 0 else "n/a",
            "Win rate (cool)":  f"{cool['correct'].mean() * 100:.1f}%" if len(cool) > 0 else "n/a",
            "Avg |surprise|":   f"{tradeable['surprise'].abs().mean():.3f}%",
        })

    return pd.DataFrame(rows)


# ── 7. Human-readable narrative ───────────────────────────────────────────────

def describe_latest_surprise(df: pd.DataFrame) -> str:
    """
    Plain-English description of the most recent CPI release.

    Usage:
        df = compute_surprises(method='ema')
        print(describe_latest_surprise(df))

    Uses ``df.attrs['surprise_method']`` when set by ``compute_surprises`` so the
    consensus line matches ema / naive / real.
    """
    method = getattr(df, "attrs", {}).get("surprise_method") or "ema"
    consensus_label = {
        "ema": "Consensus (EMA)",
        "naive": "Consensus (naive 3M avg)",
        "real": "Consensus (survey CSV)",
    }.get(method, "Consensus")

    latest    = df.dropna(subset=["surprise"]).iloc[-1]
    date_str  = latest["date"].strftime("%B %Y")
    actual    = round(latest["mom_pct"],      2)
    consensus = round(latest["consensus_mom"], 2)
    surprise  = round(latest["surprise"],      2)
    surp_z    = round(latest.get("surprise_zscore", 0), 2)
    direction = "HOT (above expectations)" if surprise > 0 else "COOL (below expectations)"
    signal    = latest["signal"]

    signal_txt = {
         1: "→ BEARISH bonds / BEARISH stocks  (hot CPI = hawkish Fed = yields up = TLT down)",
        -1: "→ BULLISH bonds / BULLISH stocks  (cool CPI = dovish Fed = yields down = TLT up)",
         0: "→ NO SIGNAL  (surprise too small to trade)",
    }.get(int(signal), "→ UNKNOWN")

    size = "LARGE" if abs(surp_z) > 1.5 else "MODERATE" if abs(surp_z) > 0.5 else "SMALL"

    return (
        f"\n{'='*60}\n"
        f"  CPI Release — {date_str}\n"
        f"{'='*60}\n"
        f"  Actual MoM:        {actual:+.2f}%\n"
        f"  {consensus_label}: {consensus:+.2f}%\n"
        f"  Surprise:          {surprise:+.2f}%  ({direction})\n"
        f"  Surprise Z-Score:  {surp_z:+.2f}  ({size} surprise)\n"
        f"\n  Trading Signal:    {signal_txt}\n"
        f"{'='*60}\n"
    )


# ── Path 3 — NFP & FOMC surprise scaffolding ────────────────────────────────


def _build_numeric_surprise_signal(
    df: pd.DataFrame,
    actual_col: str,
    consensus_col: str,
    surprise_threshold: float,
    zscore_window: int = 60,
) -> pd.DataFrame:
    """Generic surprise = actual − consensus with z-score and thresholded signal."""
    out = df.copy()
    out["surprise"] = out[actual_col] - out[consensus_col]
    roll = out["surprise"].rolling(window=zscore_window, min_periods=12)
    roll_std = roll.std().replace(0, np.nan)
    out["surprise_zscore"] = (out["surprise"] - roll.mean()) / roll_std
    out["surprise_dir"] = np.sign(out["surprise"])
    out["signal"] = out.apply(
        lambda r: int(r["surprise_dir"]) if abs(r["surprise"]) >= surprise_threshold else 0,
        axis=1,
    )
    return out


def get_nfp_monthly_change() -> pd.DataFrame:
    """Month-over-month change in nonfarm payrolls (same units as headline: thousands)."""
    df = load_series(PAYEMS).sort_values("date").reset_index(drop=True)
    df["nfp_change_k"] = df["value"].diff()
    return df.dropna(subset=["nfp_change_k"]).reset_index(drop=True)


def load_nfp_consensus_csv(filepath: str = "data/nfp_consensus.csv") -> pd.DataFrame:
    """Load survey consensus for headline payroll change (thousands).

    Required columns:
      • ``date`` or ``release_date`` — align to the same month as the FRED PAYEMS
        observation date (month-start) for the reported employment month.
      • ``consensus_nfp_k`` — expected payroll change in **thousands** (e.g. 185).
    """
    path = Path(filepath)
    if not path.is_absolute():
        path = PROJECT_ROOT / filepath
    if not path.exists():
        raise FileNotFoundError(
            f"NFP consensus file not found: {path}\n"
            "Create data/nfp_consensus.csv with columns date, consensus_nfp_k "
            "(expected headline change in thousands), or use method='ema' / 'naive'."
        )
    df = pd.read_csv(path)
    if "release_date" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"release_date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    if "consensus_nfp_k" not in df.columns:
        raise ValueError("nfp consensus CSV must include column consensus_nfp_k")
    df = df[["date", "consensus_nfp_k"]]

    hist_path = PROJECT_ROOT / "data" / "nfp_consensus_history.csv"
    if hist_path.exists() and hist_path.resolve() != path.resolve():
        h = pd.read_csv(hist_path)
        if "release_date" in h.columns and "date" not in h.columns:
            h = h.rename(columns={"release_date": "date"})
        h["date"] = pd.to_datetime(h["date"]).dt.normalize()
        if "consensus_nfp_k" not in h.columns:
            raise ValueError("nfp consensus history CSV must include column consensus_nfp_k")
        h = h[["date", "consensus_nfp_k"]]
        # Vendor/historical rows should win on overlaps (place them first).
        df = pd.concat([h, df], ignore_index=True)

    df = df.drop_duplicates(subset=["date"], keep="first").sort_values("date").reset_index(drop=True)
    return df


def compute_nfp_surprises(
    method: str = "ema",
    consensus_csv: str = "data/nfp_consensus.csv",
    surprise_threshold: float = 75.0,
    ema_span: int = 3,
    naive_window: int = 3,
) -> pd.DataFrame:
    """
    NFP surprise table (thousands of jobs): actual MoM payroll change minus expected.

    ``surprise_threshold`` is in thousands (default 75 ≈ ignore small noise).
    """
    nfp = get_nfp_monthly_change()

    if method == "ema":
        nfp = ema_consensus(nfp, value_col="nfp_change_k", span=ema_span)
        nfp = nfp.rename(columns={"consensus_ema": "consensus_nfp_k"})
        nfp = _build_numeric_surprise_signal(
            nfp, "nfp_change_k", "consensus_nfp_k", surprise_threshold
        )
    elif method == "naive":
        nfp = naive_consensus(nfp, value_col="nfp_change_k", window=naive_window)
        nfp = nfp.rename(columns={"consensus_naive": "consensus_nfp_k"})
        nfp = _build_numeric_surprise_signal(
            nfp, "nfp_change_k", "consensus_nfp_k", surprise_threshold
        )
    elif method == "real":
        cons = load_nfp_consensus_csv(consensus_csv)
        nfp = nfp.merge(cons, on="date", how="left")
        nfp = _build_numeric_surprise_signal(
            nfp, "nfp_change_k", "consensus_nfp_k", surprise_threshold
        )
    else:
        raise ValueError("method must be 'ema', 'naive', or 'real'")

    keep = [
        "date",
        "value",
        "nfp_change_k",
        "consensus_nfp_k",
        "surprise",
        "surprise_zscore",
        "surprise_dir",
        "signal",
    ]
    out = nfp[[c for c in keep if c in nfp.columns]].reset_index(drop=True)
    out.attrs["surprise_method"] = method
    out.attrs["series"] = "NFP"
    return out


def compute_fomc_surprises_scaffold(
    consensus_csv: str = "data/fomc_consensus.csv",
    probabilities_csv: str = "data/fomc_probabilities.csv",
    probabilities_history_csv: str = "data/fomc_probabilities_history.csv",
    consensus_history_csv: str = "data/fomc_consensus_history.csv",
) -> pd.DataFrame:
    """
    Minimum-viable FOMC surprise table: target upper bound (DFEDTARU) and its day-to-day change.

    Without ``data/fomc_consensus.csv`` (columns: ``date``, ``consensus_change_pp`` —
    expected change in the upper target in **percentage points**), the surprise column
    is NaN except where you merge a manual file. OIS / FedWatch implied rates are the
    next upgrade path.
    """
    df = load_series(DFEDTARU).sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.rename(columns={"value": "ff_upper_pct"})
    df["actual_change_pp"] = df["ff_upper_pct"].diff()

    # Prefer probabilities (if present) to derive a continuous expected change.
    df["consensus_change_pp"] = np.nan
    df["expected_change_pp"] = np.nan

    def _load_fomc_table(rel: str) -> pd.DataFrame | None:
        pth = PROJECT_ROOT / rel
        if not pth.exists():
            return None
        t = pd.read_csv(pth)
        if "release_date" in t.columns and "date" not in t.columns:
            t = t.rename(columns={"release_date": "date"})
        if "date" not in t.columns:
            return None
        t["date"] = pd.to_datetime(t["date"]).dt.normalize()
        return t

    p_hist = _load_fomc_table(probabilities_history_csv)
    p_fwd = _load_fomc_table(probabilities_csv)
    p_parts = [x for x in (p_hist, p_fwd) if x is not None]
    if p_parts:
        p = pd.concat(p_parts, ignore_index=True)
        if "expected_change_pp" not in p.columns:
            if "p_cut25" in p.columns and "p_hike25" in p.columns:
                p["expected_change_pp"] = (-0.25 * p["p_cut25"]) + (0.25 * p["p_hike25"])
        keep = [c for c in ["date", "expected_change_pp"] if c in p.columns]
        if "expected_change_pp" in keep:
            # Historical rows should precede forward rows in concat order; keep first on dupes.
            p = p.sort_values("date").drop_duplicates(subset=["date"], keep="first")
            df = df.drop(columns=["expected_change_pp"], errors="ignore")
            df = df.merge(p[keep], on="date", how="left")
            df["consensus_change_pp"] = df["expected_change_pp"]

    c_hist = _load_fomc_table(consensus_history_csv)
    c_fwd = _load_fomc_table(consensus_csv)
    c_parts = [x for x in (c_hist, c_fwd) if x is not None]
    if c_parts:
        c = pd.concat(c_parts, ignore_index=True)
        if "consensus_change_pp" in c.columns:
            c = c[["date", "consensus_change_pp"]]
            c = c.sort_values("date").drop_duplicates(subset=["date"], keep="first")
            df = df.merge(c, on="date", how="left", suffixes=("", "_simple"))
            df["expected_change_pp"] = df["expected_change_pp"].where(
                df["expected_change_pp"].notna(), df["consensus_change_pp"]
            )

    df["surprise_pp"] = df["actual_change_pp"] - df["expected_change_pp"]
    # Meeting day flag:
    # - True when the date is in the consensus file (so you can evaluate "hold" surprises too)
    # - OR when the target actually moved (for history / when consensus is missing).
    is_listed_meeting = df["expected_change_pp"].notna()
    df["meeting_day"] = is_listed_meeting | (df["actual_change_pp"].abs() >= 0.005)
    df.attrs["series"] = "FOMC_scaffold"
    return df


# ── __main__ ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _csv = "data/cpi_consensus.csv"
    _csv_abs = PROJECT_ROOT / _csv

    # Survey-based REAL consensus needs data/cpi_consensus.csv. Try Cleveland Fed once
    # if missing (needs network); otherwise skip REAL demos without noisy warnings.
    if not _csv_abs.exists():
        print(
            "\nNote: data/cpi_consensus.csv is missing (needed for method='real').\n"
            "Attempting Cleveland Fed download to build it…"
        )
        try:
            from mini_hedge.fetchers import fetch_cleveland_fed

            fetch_cleveland_fed(save_csv=True, csv_path=_csv_abs)
            print(f"  ✓  Wrote {_csv_abs}\n")
        except Exception as exc:
            print(
                f"  (Cleveland Fed auto-build failed: {exc})\n"
                "  REAL consensus will be skipped. You can still use naive/ema, or add the CSV manually.\n"
            )

    _run_real = _csv_abs.exists()
    if not _run_real:
        print(
            "Skipping REAL consensus in this run — add data/cpi_consensus.csv or fix network, then re-run.\n"
            "  Docs: https://www.investing.com/economic-calendar/cpi-733\n"
        )

    print("Comparing consensus methods...\n")
    comparison = compare_consensus_methods(
        consensus_csv=_csv,
        auto_fetch_consensus=False,
        include_real=_run_real,
    )
    print(comparison.to_string(index=False))

    for method in ("naive", "ema") + (("real",) if _run_real else ()):
        print(f"\n--- Latest release ({method.upper()} method) ---")
        try:
            if method == "real":
                df = compute_surprises(
                    method="real",
                    consensus_csv=_csv,
                    auto_fetch_consensus=False,
                )
            else:
                df = compute_surprises(method=method)
            print(describe_latest_surprise(df))
        except Exception as exc:
            print(f"  (skipped — {exc})")

    print("\n--- Signal counts ---")
    for method in ("naive", "ema") + (("real",) if _run_real else ()):
        try:
            if method == "real":
                df = compute_surprises(
                    method="real",
                    consensus_csv=_csv,
                    auto_fetch_consensus=False,
                )
            else:
                df = compute_surprises(method=method)
            h = (df["signal"] == 1).sum()
            c = (df["signal"] == -1).sum()
            n = (df["signal"] == 0).sum()
            print(f"  {method.upper():6s}: hot={h}  cool={c}  none={n}")
        except Exception as exc:
            print(f"  {method.upper():6s}: (skipped — {exc})")
