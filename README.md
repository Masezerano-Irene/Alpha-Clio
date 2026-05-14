# Mini Hedge
Personal macro research stack: pull CPI and rates from FRED/BLS into SQLite, derive MoM/YoY/z-scores and **CPI surprise** signals (naive / EMA / survey CSV consensus), and relate releases to Treasury yield moves for event-style analysis.
**Path 3 (vol + macro):** `^VIX` / `^MOVE` live in a dedicated `vol_indices` table; `transforms.realized_volatility` and IV–RV-style spreads; **NFP** and **FOMC** surprise scaffolding in `surprises.py`; `event_study.py` for window returns and vol tags. See `notebooks/03_market_reactions.ipynb`.

**Stack:** Python, pandas, SQLite, matplotlib, yfinance · Jupyter notebooks for exploration.
## Setup
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
Copy `.env.example` to `.env` and add API keys (FRED, BLS) as needed. Bootstrap local data:
```bash
python scripts/bootstrap_db.py
```
## Repo layout
- `mini_hedge/` — transforms, surprises, prices, fetchers, storage  
- `notebooks/` — derived signals dashboard  
- `data/` — local DB (`econ.db`), optional `cpi_consensus.csv`, `nfp_consensus.csv` (columns `date`, `consensus_nfp_k`), optional `fomc_consensus.csv` (`date`, `consensus_change_pp`)  
This project is under active development.

## Backtesting workflow (verified baseline)
1. Build/update the event panel:
```bash
python3 -m mini_hedge.cli export-phase3
```
2. Run the baseline backtest:
```bash
python3 -m mini_hedge.cli backtest --train-end 2022-12-31
```

## Public repository note
To keep private research material off public GitHub, the `data/` and `docs/` directories are intentionally excluded from version control.
Reviewers can still evaluate engineering quality from the tracked code (`mini_hedge/`, `scripts/`, tests, and CLI flows) and reproduce pipeline behavior by generating local data with the documented bootstrap/backtest commands.
Private evidence documents and raw datasets are available separately on request.


Outputs are written to `data/derived/backtests/<run_id>/` and include:
- `equity_curve.csv`, `daily_returns.csv`, `event_returns.csv`, `trades.csv`
- `summary_metrics.csv`, `split_metrics.csv`, `sensitivity_grid.csv`
- `equity_curve.png`, `drawdown_curve.png`, `rolling_sharpe.png`
- `portfolio_report.md` (generated report with reproducibility command)
