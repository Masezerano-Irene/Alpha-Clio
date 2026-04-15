# Mini Hedge
Personal macro research stack: pull CPI and rates from FRED/BLS into SQLite, derive MoM/YoY/z-scores and **CPI surprise** signals (naive / EMA / survey CSV consensus), and relate releases to Treasury yield moves for event-style analysis.
**Stack:** Python, pandas, SQLite, matplotlib · Jupyter notebooks for exploration.
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
- `data/` — local DB (`econ.db`) and optional `cpi_consensus.csv` for survey consensus  
This project is under active development.
