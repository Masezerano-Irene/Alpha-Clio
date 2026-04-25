from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mini_hedge.config import PROJECT_ROOT


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if "release_date" in df.columns and "event_date" not in df.columns:
        df = df.rename(columns={"release_date": "event_date"})
    if "date" not in df.columns or "event_date" not in df.columns:
        raise ValueError("Input must include `date` (payroll month-start) and `event_date` (release day).")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["event_date"] = pd.to_datetime(df["event_date"]).dt.normalize()
    return df[["date", "event_date"]].sort_values("date").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge vendor/historical NFP release dates into data/nfp_release_calendar_history.csv")
    ap.add_argument(
        "input_csv",
        nargs="?",
        default=str(PROJECT_ROOT / "data" / "nfp_release_calendar.csv"),
        help="Input CSV path (default: data/nfp_release_calendar.csv)",
    )
    ap.add_argument(
        "--dest",
        default=str(PROJECT_ROOT / "data" / "nfp_release_calendar_history.csv"),
        help="Destination path (default: data/nfp_release_calendar_history.csv)",
    )
    args = ap.parse_args()

    input_path = Path(args.input_csv)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    if not input_path.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {input_path}\n\n"
            "Provide a path explicitly, e.g.\n"
            "  python scripts/ingest_nfp_release_calendar_history.py path/to/file.csv\n\n"
            "Or create data/nfp_release_calendar.csv with columns `date` and `event_date`."
        )

    inc = _normalize(pd.read_csv(input_path))
    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        cur = _normalize(pd.read_csv(dest))
        out = pd.concat([cur, inc], ignore_index=True)
    else:
        out = inc

    out = out.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    out.to_csv(dest, index=False)
    print(f"Wrote {len(out):,} rows to {dest}")


if __name__ == "__main__":
    main()
