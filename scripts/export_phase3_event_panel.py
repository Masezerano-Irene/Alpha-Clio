from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_DATA_DIR = _REPO_ROOT / "data"

from mini_hedge import fetchers
from mini_hedge.event_study import forward_close_returns, tag_events_with_vol
from mini_hedge.prices import fetch_yfinance, get_release_dates
from mini_hedge.surprises import (
    compute_fomc_surprises_scaffold,
    compute_nfp_surprises,
    compute_surprises,
)


@dataclass(frozen=True)
class PanelParams:
    horizons: tuple[int, ...] = (0, 1, 5)
    vol_lookback_days: int = 252
    vol_percentile_lookback_days: int = 1260
    realized_vol_window: tuple[int, int] = (0, 5)
    assumed_cost_bps: float = 1.0
    cpi_method: str = "real"
    nfp_method: str = "real"
    # FOMC uses expected_change_pp from probabilities when present.
    fomc_probabilities_csv: str = str(_DATA_DIR / "fomc_probabilities.csv")
    fomc_consensus_csv: str = str(_DATA_DIR / "fomc_consensus.csv")


def _git_head_hash() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                text=True,
                cwd=_REPO_ROOT,
                stderr=subprocess.DEVNULL,
            )
            .strip()
        )
    except Exception:
        return "UNKNOWN"


def _bucket_z(z: float) -> str:
    if z is None or (isinstance(z, float) and np.isnan(z)):
        return "missing"
    if z <= -1.5:
        return "<=-1.5"
    if z <= -0.5:
        return "(-1.5,-0.5]"
    if z < 0.5:
        return "(-0.5,0.5)"
    if z < 1.5:
        return "[0.5,1.5)"
    return ">=1.5"


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def build_phase3_event_panel(params: PanelParams) -> tuple[pd.DataFrame, dict]:
    commit = _git_head_hash()

    # Refresh external inputs needed for event dates / expectations.
    # (CPI consensus already lives in data/cpi_consensus.csv; NFP/FOMC refresh optional but cheap.)
    fetchers.fetch_investing_nfp_release_calendar(save_csv=True)
    fetchers.fetch_investing_nfp_forecasts(save_csv=True)
    fetchers.fetch_rateprobability_fomc_consensus(save_csv=True)
    fetchers.fetch_rateprobability_fomc_probabilities(save_csv=True)

    # Prices for forward returns & realized vol tags
    spy = fetch_yfinance("SPY", start="1993-01-29")
    tlt = fetch_yfinance("TLT", start="2002-07-26")
    uup = fetch_yfinance("UUP", start="2007-03-01")

    # ── CPI events ────────────────────────────────────────────────────────────
    cpi_consensus_path = str(_DATA_DIR / "cpi_consensus.csv")
    cpi_s = compute_surprises(
        method=params.cpi_method,
        consensus_csv=cpi_consensus_path,
        auto_fetch_consensus=False,
    )
    cpi_s = cpi_s.dropna(subset=["surprise"]).copy()
    cpi_s["ref_month"] = cpi_s["date"].dt.to_period("M").dt.to_timestamp()

    cpi_releases = pd.DataFrame({"event_date": pd.to_datetime(get_release_dates(cpi_consensus_path))})
    cpi_releases["ref_month"] = (
        cpi_releases["event_date"] - pd.DateOffset(months=1)
    ).dt.to_period("M").dt.to_timestamp()
    cpi_ev = cpi_releases.merge(
        cpi_s[
            [
                "ref_month",
                "surprise",
                "surprise_zscore",
                "signal",
            ]
        ],
        on="ref_month",
        how="left",
    ).dropna(subset=["surprise"])
    cpi_ev["event_type"] = "CPI"

    # ── NFP events ────────────────────────────────────────────────────────────
    nfp_s = compute_nfp_surprises(
        method=params.nfp_method,
        consensus_csv=str(_DATA_DIR / "nfp_consensus.csv"),
    )
    nfp_s = nfp_s.dropna(subset=["surprise"]).copy()
    nfp_s["date"] = pd.to_datetime(nfp_s["date"]).dt.normalize()

    cal = pd.read_csv(_DATA_DIR / "nfp_release_calendar.csv")
    cal["date"] = pd.to_datetime(cal["date"]).dt.normalize()
    cal["event_date"] = pd.to_datetime(cal["event_date"]).dt.normalize()

    nfp_ev = cal.merge(
        nfp_s[["date", "surprise", "surprise_zscore", "signal"]],
        on="date",
        how="inner",
    )
    nfp_ev["event_type"] = "NFP"

    # ── FOMC events ───────────────────────────────────────────────────────────
    fomc = compute_fomc_surprises_scaffold(
        consensus_csv=params.fomc_consensus_csv,
        probabilities_csv=params.fomc_probabilities_csv,
    )
    fomc = fomc[fomc["meeting_day"]].copy()
    fomc = fomc.dropna(subset=["expected_change_pp", "surprise_pp"])
    # Create a z-score across meeting surprises (not daily rows)
    fomc = fomc.sort_values("date").reset_index(drop=True)
    roll = fomc["surprise_pp"].rolling(window=60, min_periods=12)
    std = roll.std().replace(0, np.nan)
    fomc["surprise_zscore"] = (fomc["surprise_pp"] - roll.mean()) / std
    fomc["surprise"] = fomc["surprise_pp"]
    fomc["signal"] = np.sign(fomc["surprise"]).astype(int)
    fomc["event_date"] = pd.to_datetime(fomc["date"]).dt.normalize()
    fomc_ev = fomc[["event_date", "surprise", "surprise_zscore", "signal"]].copy()
    fomc_ev["event_type"] = "FOMC"

    # ── Combine events ─────────────────────────────────────────────────────────
    events = pd.concat(
        [
            cpi_ev[["event_date", "event_type", "surprise", "surprise_zscore", "signal"]],
            nfp_ev[["event_date", "event_type", "surprise", "surprise_zscore", "signal"]],
            fomc_ev[["event_date", "event_type", "surprise", "surprise_zscore", "signal"]],
        ],
        ignore_index=True,
    ).sort_values(["event_date", "event_type"]).reset_index(drop=True)

    # Buckets
    events["surprise_bucket_z"] = events["surprise_zscore"].apply(_bucket_z)
    events["surprise_bucket_dir"] = events["surprise"].apply(
        lambda x: "missing" if pd.isna(x) else ("neg" if x < 0 else "pos" if x > 0 else "zero")
    )

    spy_ret = forward_close_returns(spy, events, event_date_col="event_date", horizons=params.horizons)
    tlt_ret = forward_close_returns(tlt, events, event_date_col="event_date", horizons=params.horizons)
    uup_ret = forward_close_returns(uup, events, event_date_col="event_date", horizons=params.horizons)
    for h in params.horizons:
        spy_ret = spy_ret.rename(columns={f"ret_h{h}": f"spy_ret_h{h}"})
        tlt_ret = tlt_ret.rename(columns={f"ret_h{h}": f"tlt_ret_h{h}"})
        uup_ret = uup_ret.rename(columns={f"ret_h{h}": f"uup_ret_h{h}"})
    panel = events.merge(spy_ret[["event_date"] + [f"spy_ret_h{h}" for h in params.horizons]], on="event_date", how="left")
    panel = panel.merge(tlt_ret[["event_date"] + [f"tlt_ret_h{h}" for h in params.horizons]], on="event_date", how="left")
    panel = panel.merge(uup_ret[["event_date"] + [f"uup_ret_h{h}" for h in params.horizons]], on="event_date", how="left")

    # Pre-event IV, percentiles, realized vol, vol miss
    panel = tag_events_with_vol(
        panel,
        event_date_col="event_date",
        spy_prices=spy,
        tlt_prices=tlt,
        uup_prices=uup,
        lookback_days=params.vol_lookback_days,
        vol_percentile_lookback_days=params.vol_percentile_lookback_days,
    )

    # Canonical column names for downstream backtests
    panel["surprise_z"] = panel["surprise_zscore"]
    panel["event_id"] = panel["event_type"] + "_" + panel["event_date"].dt.strftime("%Y-%m-%d")

    # Percentiles as 0..100 (tag_events_with_vol stores 0..1 ranks)
    if "vix_pre_pctile" in panel.columns:
        panel["vix_pre_vol_pct"] = panel["vix_pre_pctile"] * 100.0
    if "move_pre_pctile" in panel.columns:
        panel["move_pre_vol_pct"] = panel["move_pre_pctile"] * 100.0

    # Params / costs columns
    panel["assumed_cost_bps"] = params.assumed_cost_bps
    panel["git_commit"] = commit

    # Freeze a stable schema (avoid duplicate surprise_z columns, drop raw percentile 0..1)
    cols = [
        "event_id",
        "event_date",
        "event_type",
        "surprise",
        "surprise_z",
        "signal",
        "surprise_bucket_z",
        "surprise_bucket_dir",
    ]
    for h in params.horizons:
        cols += [f"spy_ret_h{h}", f"tlt_ret_h{h}", f"uup_ret_h{h}"]
    cols += [
        "vix_pre",
        "move_pre",
        "vix_pre_vol_pct",
        "move_pre_vol_pct",
        "rv_spy_h0_h5_ann",
        "rv_tlt_h0_h5_ann",
        "rv_uup_h0_h5_ann",
        "vol_miss_spy",
        "vol_miss_tlt",
        "vol_miss_uup",
        "assumed_cost_bps",
        "git_commit",
    ]
    panel = panel[[c for c in cols if c in panel.columns]].copy()

    meta = {
        "git_commit": commit,
        "generated_at_utc": pd.Timestamp.now("UTC").isoformat(),
        "row_count": int(len(panel)),
        "params": asdict(params),
        "notes": [
            "CPI event_date uses merged CPI release dates (hardcoded + data/cpi_consensus.csv wins on overlaps) and maps to prior-month CPI surprise.",
            "NFP event_date is scraped from Investing.com and mapped to payroll month via '(Mon)' token.",
            "FOMC expected_change_pp prefers data/fomc_probabilities_history.csv (if present) then data/fomc_probabilities.csv; consensus prefers data/fomc_consensus_history.csv then data/fomc_consensus.csv.",
            "If vix_pre/move_pre are empty, run: python3 -m mini_hedge.cli fetch-vol (requires yfinance + local SQLite vol_indices).",
        ],
    }
    return panel, meta


def main() -> None:
    params = PanelParams()
    panel, meta = build_phase3_event_panel(params)

    out_dir = _DATA_DIR / "exports"
    _ensure_dir(out_dir)

    csv_path = out_dir / "phase3_event_panel.csv"
    panel.to_csv(csv_path, index=False)

    parquet_path = out_dir / "phase3_event_panel.parquet"
    try:
        panel.to_parquet(parquet_path, index=False, engine="pyarrow")
        wrote_parquet = True
    except Exception as exc:
        wrote_parquet = False
        meta["parquet_error"] = str(exc)

    meta_path = out_dir / "phase3_event_panel.meta.json"
    meta["files"] = {
        "csv": str(csv_path),
        "parquet": str(parquet_path) if wrote_parquet else None,
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))

    print(f"Wrote {len(panel):,} rows to {csv_path}")
    if wrote_parquet:
        print(f"Wrote {len(panel):,} rows to {parquet_path}")
    print(f"Wrote metadata to {meta_path}")
    print(f"git_commit = {meta['git_commit']}")


if __name__ == "__main__":
    main()

