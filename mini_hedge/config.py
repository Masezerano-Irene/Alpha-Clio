"""Centralized configuration — loads API keys from .env, exposes constants."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# API keys (read from environment after dotenv populates it)
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
BLS_API_KEY = os.environ.get("BLS_API_KEY", "")

# API endpoints
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
BLS_BASE = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Storage
DB_PATH = PROJECT_ROOT / "data" / "econ.db"

# Ingestion: when True, API pulls try to load all available history (stored in SQLite;
# new releases overwrite/append the same dates on each run). When False, only the last
# DEFAULT_FETCH_MONTHS window is requested unless you pass an explicit fetch_months int.
FETCH_FULL_HISTORY = True

# Earliest calendar year to request from BLS in full-history mode (CPI-U exists from 1913).
BLS_FULL_HISTORY_START_YEAR = 1913

# Used only when FETCH_FULL_HISTORY is False and fetch_months is omitted.
DEFAULT_FETCH_MONTHS = 120

# CLI / tables: how many most-recent rows to print when [N] is omitted (ingestion still full
# when FETCH_FULL_HISTORY is True).
DEFAULT_DISPLAY_MONTHS = 12
