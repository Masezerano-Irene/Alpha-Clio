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
