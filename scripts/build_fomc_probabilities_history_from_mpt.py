from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mini_hedge import storage


def _mpt_last_pre_meeting_expected_rate_units(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per meeting with the last pre-meeting implied level.

    Prefer Atlanta Fed's published ``Rate: mean`` (matches their summary stats). If it
    is missing for some meetings, fall back to reconstructing the mean from the
    ``Prob: <lo>bps - <hi>bps`` rows using bin midpoints (can disagree slightly).
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["reference_start"] = pd.to_datetime(df["reference_start"]).dt.normalize()

    mean = df[df["field"].astype(str) == "Rate: mean"].copy()
    mean["expected_rate_units"] = pd.to_numeric(mean["value"], errors="coerce")
    mean = mean.dropna(subset=["expected_rate_units", "date", "reference_start"])
    mean_before = mean[mean["date"] < mean["reference_start"]].copy()
    if mean_before.empty:
        mean_last = pd.DataFrame(columns=["meeting_date", "asof", "expected_rate_units"])
    else:
        mean_last = (
            mean_before.sort_values(["reference_start", "date"])
            .groupby("reference_start", as_index=False)
            .tail(1)
            .rename(columns={"reference_start": "meeting_date", "date": "asof"})[
                ["meeting_date", "asof", "expected_rate_units"]
            ]
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
    if before.empty:
        prob_last = pd.DataFrame(columns=["meeting_date", "asof", "expected_rate_units"])
    else:
        prob_last = (
            before.sort_values(["reference_start", "date"])
            .groupby("reference_start", as_index=False)
            .tail(1)
            .rename(columns={"reference_start": "meeting_date", "date": "asof"})[
                ["meeting_date", "asof", "expected_rate_units"]
            ]
        )

    if mean_last.empty and prob_last.empty:
        raise RuntimeError("No pre-meeting observations found in MPT histdata workbook.")

    if mean_last.empty:
        return prob_last.sort_values("meeting_date").reset_index(drop=True)
    if prob_last.empty:
        return mean_last.sort_values("meeting_date").reset_index(drop=True)

    merged = mean_last.merge(
        prob_last,
        on="meeting_date",
        how="outer",
        suffixes=("_mean", "_prob"),
        indicator=True,
    )
    # Prefer mean where present; otherwise fall back to prob reconstruction.
    merged["asof"] = merged["asof_mean"].combine_first(merged["asof_prob"])
    merged["expected_rate_units"] = merged["expected_rate_units_mean"].combine_first(
        merged["expected_rate_units_prob"]
    )
    return merged[["meeting_date", "asof", "expected_rate_units"]].sort_values("meeting_date").reset_index(drop=True)


def main() -> None:
    xlsx = _REPO_ROOT / "data" / "mpt_histdata.xlsx"
    if not xlsx.exists():
        raise FileNotFoundError(
            f"Missing {xlsx}. Download from Atlanta Fed MPT Historical Data first."
        )

    df = pd.read_excel(xlsx, sheet_name="DATA")

    last = _mpt_last_pre_meeting_expected_rate_units(df)

    ff = storage.query_series("DFEDTARU").copy()
    ff["date"] = pd.to_datetime(ff["date"]).dt.normalize()
    ff = ff.rename(columns={"value": "ff_upper_pct"})[["date", "ff_upper_pct"]].sort_values("date")

    out = last.merge(ff, left_on="asof", right_on="date", how="left", suffixes=("", "_ff"))
    # avoid duplicate 'date' when we later rename meeting_date -> date
    out = out.drop(columns=["date"], errors="ignore")
    # Atlanta Fed MPT stores implied levels on a 0–100 scale where the implied target
    # upper bound in *percent points* is `level / 100` (this matches `DFEDTARU` in FRED).
    out["expected_rate_pct"] = out["expected_rate_units"] / 100.0
    out["expected_change_pp"] = out["expected_rate_pct"] - out["ff_upper_pct"]

    res = out.rename(columns={"meeting_date": "date"})[["date", "expected_change_pp"]].dropna()
    res = res.sort_values("date").reset_index(drop=True)

    dest = _REPO_ROOT / "data" / "fomc_probabilities_history.csv"
    res.to_csv(dest, index=False)
    print(f"Wrote {len(res):,} rows to {dest}")


if __name__ == "__main__":
    main()

