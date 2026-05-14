# Alpha Clio — Macro Event Investment Analytics Platform

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![Status](https://img.shields.io/badge/Status-In%20Development-orange)
![Data](https://img.shields.io/badge/Data-FRED%20%7C%20BLS%20%7C%20OANDA%20%7C%20Alpaca-green)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

> A Python investment analytics platform that models macro-driven investment opportunities across US Treasuries, equities, and the dollar index — built as a quantitative research portfolio piece and behavioral-finance discipline framework.

---

## What This Project Does

- Built a Python investment analytics platform to model and evaluate macro-driven investment opportunities; automated ingestion of CPI, NFP, and FOMC release data from FRED and BLS into a structured event panel spanning 2009–2026; engineered return calculations and rolling z-score risk metrics across 365+ macro release observations (NFP: 136, CPI: 216), measuring investment performance outcomes across 1-, 2-, and 5-day windows for three asset classes — US Treasuries, equities, and the dollar index.

- Developed and evaluated z-score-normalized economic surprise signals to predict investment direction; backtested signal performance across 107 discrete investment decisions over 4,454 trading days; identified that next-day return measurement introduced a timing lag that suppressed signal accuracy, quantified the root cause, and redesigned the methodology to a 5-minute intraday event window — documenting all findings, assumptions, and remedial action in structured analytical reports suitable for management review.

---

## Key Results

All numbers below are from actual backtest runs on real market data (FRED, BLS, Yahoo Finance).

| Metric | Value |
|---|---|
| Total events analyzed | 365+ macro releases (NFP: 136, CPI: 216, FOMC: 13) |
| Backtest period | February 2009 – March 2026 (4,454 trading days) |
| Tradeable signals identified | 107 across full history |
| Asset classes covered | TLT (Treasuries), SPY (Equities), UUP (Dollar Index) |
| Return windows measured | 1-day, 2-day, 5-day post-release |
| Out-of-sample period | 2023–2026 (16 events) |
| Out-of-sample Sharpe | 0.95 |

**Key analytical finding:** The initial daily-return methodology introduced a 30-hour timing lag between signal and measurement. Diagnosing and correcting this — redesigning from next-day close to 5-minute intraday event windows — was the central methodological contribution of Phase 1.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                               │
│  FRED API → CPI, NFP, FOMC      OANDA API → EUR/USD, USD/JPY   │
│  BLS API  → Employment data     Alpaca API → TLT, SPY           │
│  Bloomberg CSV → Historical     IBKR TWS  → Live accumulation   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SIGNAL LAYER                               │
│  surprise_z = (actual − consensus) / historical_std             │
│  3-Tier Classification:                                         │
│    Tier 1 (|z| ≥ 0.8) → NFP, CPI, FOMC, PCE   → 100% size     │
│    Tier 2 (|z| ≥ 1.2) → ISM, Claims, Retail    →  75% size     │
│    Tier 3 (|z| ≥ 1.5) → Housing, Durable, GDP  →  50% size     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      REGIME LAYER                               │
│  VIX < 20  → NORMAL   : all instruments at standard size        │
│  VIX 20-25 → ELEVATED : monitor only, no size change            │
│  VIX 25-35 → STRESS   : USD/JPY at 150% (carry amplification)  │
│  VIX > 35  → PANIC    : USD/JPY + CL paused; GC + TLT hold     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EXIT LAYER                                  │
│  Rule 1 — Hard Stop  : −2 bps within first 30 seconds          │
│  Rule 2 — HWM Trail  : 60% giveback from peak (if peak ≥ 1.5)  │
│  Rule 3 — Time Exit  : max 300s (270s for FOMC)                 │
│  Test horizons: 3min / 5min / 7min / 10min / 15min              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ANALYTICS LAYER                               │
│  • Signal accuracy (hit rate by tier / instrument / regime)     │
│  • Cross-instrument correlation & factor concentration (PCA)    │
│  • Basis risk: co-hit rate and conflicting signal detection      │
│  • Performance attribution: expected vs actual by event type    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Portfolio — 5 Instruments, 4 Distinct Factors

| Instrument | Asset | Primary Factor | Regime Behaviour |
|---|---|---|---|
| TLT | 20-yr Treasury ETF | Nominal rates / duration | Safe-haven in panic — holds 100% |
| EUR/USD | Euro / Dollar FX | Dollar strength signal | Reduced to 50% in panic |
| USD/JPY | Dollar / Yen FX | Dollar + JPY carry hedge | 150% in stress; paused in panic |
| CL | Crude Oil Futures | Energy / global growth | Paused in panic (demand collapse) |
| GC | Gold Futures | Real rates / inflation hedge | Safe-haven in panic — holds 100% |

> **Design note:** EUR/USD and USD/JPY may appear redundant as both FX pairs respond to the dollar. USD/JPY was retained for its unique carry-trade component: in stress regimes (VIX 25–35), JPY strengthens independently of the macro surprise signal due to carry unwind, providing conditional diversification precisely when the TLT position is most at risk.

---

## Event Calendar — 13 Events, ~184 Releases/Year

| Event | Tier | Release ET | Instruments | ~N/yr |
|---|---|---|---|---|
| Non-Farm Payrolls | 1 | 08:30 | TLT, EUR/USD, USD/JPY, CL | 12 |
| CPI | 1 | 08:30 | TLT, EUR/USD, USD/JPY, GC | 12 |
| FOMC Rate Decision | 1 | 14:00 | TLT, EUR/USD, USD/JPY, GC | 8 |
| PCE Price Index | 1 | 08:30 | TLT, EUR/USD, USD/JPY, GC | 12 |
| Initial Jobless Claims | 2 | 08:30 | TLT, EUR/USD, USD/JPY | 52 |
| ISM Manufacturing PMI | 2 | 10:00 | EUR/USD, USD/JPY, CL | 12 |
| ISM Services PMI | 2 | 10:00 | EUR/USD, USD/JPY, CL | 12 |
| Retail Sales | 2 | 08:30 | TLT, EUR/USD, USD/JPY | 12 |
| PPI | 2 | 08:30 | TLT, EUR/USD, USD/JPY, GC | 12 |
| Housing Starts | 3 | 08:30 | EUR/USD, USD/JPY | 12 |
| Durable Goods | 3 | 08:30 | EUR/USD, USD/JPY | 12 |
| Consumer Confidence | 3 | 10:00 | EUR/USD, USD/JPY | 12 |
| GDP | 3 | 08:30 | EUR/USD, USD/JPY, CL | 4 |

---

## Project Structure

```
alpha-clio/
├── mini_hedge/
│   ├── event_calendar.py      # 13 events, 3-tier system, instrument mapping
│   ├── regime.py              # VIX classifier, per-instrument size multipliers
│   ├── exit_logic.py          # 3-rule asymmetric exit system
│   ├── analytics.py           # Signal accuracy, basis risk, factor concentration
│   ├── intraday_backtest.py   # 5-minute event window engine + 2D parameter grid
│   ├── intraday_costs.py      # Time-dependent cost model (base/stress/panic)
│   ├── data_loader.py         # Unified loader: Bloomberg + Alpaca + IBKR
│   ├── alpaca_fetcher.py      # Alpaca Markets API → TLT/SPY 1-min bars
│   ├── oanda_fetcher.py       # OANDA v20 API → EUR/USD, USD/JPY 1-min bars
│   ├── bloomberg_importer.py  # Bloomberg CSV → parquet cache
│   └── ibkr_fetcher.py        # IBKR TWS → live 1-min bar accumulation
├── data/
│   ├── exports/               # Sprint result tables (NFP, CPI, FOMC)
│   ├── derived/backtests/     # Backtest outputs: trades, equity curve, metrics
│   └── *.csv                  # Consensus, surprise, and calendar data
├── notebooks/
│   ├── 02_derived_signals.ipynb
│   └── 03_market_reactions.ipynb
├── scripts/
│   └── econ.ipynb
├── docs/
│   └── backtest_strategy_spec.md
├── requirements.txt
└── README.md
```

---

## Methodology — Step by Step

### Step 1 — Surprise Signal Construction
Economic surprises are normalised using z-scores:

```
surprise_z = (actual_release − consensus_forecast) / std(historical_surprises)
```

The standard deviation is computed over all prior releases for that event type, using an expanding window to avoid lookahead bias. A positive surprise_z on CPI means inflation came in hotter than economists expected. A negative surprise_z on NFP means fewer jobs were created than forecast.

### Step 2 — Signal Filtering by Tier
Only events where `|surprise_z|` exceeds the tier threshold are traded:
- Tier 1: `|z| ≥ 0.8` — large, high-conviction surprises
- Tier 2: `|z| ≥ 1.2` — medium surprises with supporting conditions
- Tier 3: `|z| ≥ 1.5` — only the largest surprises on lower-impact events

### Step 3 — Regime Assessment
Prior-day VIX close is used to classify the market regime before any trade is opened. The regime determines per-instrument position size multipliers (see table above). The regime layer never creates or cancels a trade — it only scales the size of positions already authorised by the signal layer.

### Step 4 — Entry and Exit
Entry is placed at the 8:30 ET open bar (or 14:00 for FOMC). Three exit rules run simultaneously on every 1-minute bar:
1. Hard stop if loss exceeds 2 bps in first 30 seconds
2. Trail exit if trade retraces 60% from its peak gain
3. Time exit at 300 seconds (270s for FOMC, before the press conference)

### Step 5 — Attribution and Validation
Every trade is attributed by: instrument, event type, tier, z-score bucket, and VIX regime. Validation uses a locked 20% holdout with Newey-West adjusted t-statistics and block bootstrap confidence intervals for Sharpe ratio.

---

## Key Methodological Finding

The initial backtest measured returns at next-day market close — introducing a 30-hour gap between the 8:30 ET release and the return measurement point. During that window, unrelated market movements swamped the event signal, producing a near-zero Sharpe ratio (0.089).

Redesigning the measurement to a 5-minute intraday window — capturing only the price movement directly attributable to the release — eliminated this confound. This diagnostic finding, and the methodology correction it produced, is the central analytical contribution of Phase 1.

```
Before fix:  signal at 8:30 ET → return measured at next-day 16:00 ET
             gap = 30 hours of noise → Sharpe 0.089

After fix:   signal at 8:30 ET → return measured at 8:35 ET
             window = 5 minutes of signal → intraday methodology
```

---

## Execution Cost Model

| Regime | Cost Assumption | Basis |
|---|---|---|
| Base (VIX < 20) | 10 bps round-trip | Conservative baseline |
| Stress (VIX 25–35) | 15 bps | Wider spreads in risk-off |
| Panic (VIX > 35) | 20 bps | Liquidity-adjusted |

**Validation against real data:** Level 2 tick data from 2-year Treasury futures (ZT) showed actual round-trip execution costs of ~0.79 bps during normal market conditions — confirming the 10 bps baseline provides a 12x safety margin against actual observed costs.

---

## Validation Framework

Before any live or paper trading begins, the system must pass a formal Go/No-Go gate on the locked holdout:

| Criterion | Threshold |
|---|---|
| Newey-West adjusted Sharpe (holdout) | ≥ 0.50 |
| Maximum drawdown (holdout) | ≤ 15% |
| Stress-period expectancy | ≥ 0 bps |
| Single-event concentration | ≤ 40% of total P&L |
| Signal log completeness | ≥ 95% of expected events |

No criterion can be waived. Paper trading begins only after all five are met.

---

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/alpha-clio.git
cd alpha-clio
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**API credentials** — create a `.env` file in the project root:

```
ALPACA_API_KEY=your_key
ALPACA_API_SECRET=your_secret
OANDA_API_TOKEN=your_token
OANDA_ACCOUNT_TYPE=practice
```

---

## Data Sources

| Source | Data | Coverage | Cost |
|---|---|---|---|
| FRED (St. Louis Fed) | CPI, NFP actuals | 2000–present | Free |
| BLS API | Employment data | 2000–present | Free |
| OANDA v20 API | EUR/USD, USD/JPY 1-min bars | 2005–present | Free |
| Alpaca Markets API | TLT, SPY 1-min bars | 2016–present | Free |
| IBKR TWS (ib_insync) | CL, GC futures; live accumulation | 2021–present | Free with account |
| Bloomberg Terminal | Historical CSV export (TLT, CL, GC) | 2008–2015 | University access |
| Yahoo Finance (yfinance) | VIX daily close | 2000–present | Free |

---

## Roadmap

- [x] Phase 0 — Event calendar, signal construction, consensus data collection
- [x] Phase 1 — Daily backtest, methodology diagnosis, cost model validation
- [x] Phase 2 — Intraday backtest engine, asymmetric exit system, regime classifier
- [x] Phase 3 — 5-instrument portfolio, analytics module, factor concentration analysis
- [ ] Phase 4 — Data collection (Alpaca/OANDA fetch, Bloomberg import)
- [ ] Phase 5 — Full intraday backtest across all 5 instruments, Go/No-Go gate
- [ ] Phase 6 — Paper trading on IBKR simulated environment
- [ ] Phase 7 — Live deployment (post paper-trading validation)

---

## Technologies

| Category | Tools |
|---|---|
| Language | Python 3.11+ |
| Data manipulation | pandas, numpy, pyarrow |
| Market data | alpaca-py, oandapyV20, ib_insync, yfinance |
| Storage | SQLite, Parquet |
| Visualisation | matplotlib (Agg backend — headless) |
| Statistics | scipy, statsmodels (Newey-West) |
| Version control | Git / GitHub |

---

## Academic Context

This project was developed alongside graduate coursework at Brandeis University International Business School (M.S. Business Analytics, GPA 3.64):

- **BUS 294A** — Machine Learning for Inflation Event Studies *(A)*
- **FIN 253A** — Advanced Quantitative Analysis in Finance *(A)*
- **ECON/FIN 250A** — Forecasting in Finance and Economics *(A-)*
- **ECON 213A** — Applied Econometrics with R *(B+)*
- **BUS/FIN 241A** — Machine Learning and Data Analysis for Business and Finance *(B+)*

The behavioral-finance motivation — building a rules-based system that removes discretionary judgment from investment decisions — draws on Hirschey & Nofsinger's framework for systematic investment discipline.

---

## Author

**Irene Masezerano**
M.S. Business Analytics — Brandeis University (May 2026)
[LinkedIn](https://linkedin.com) · [Email](mailto:masezirene@gmail.com)

---

*Alpha Clio is a research and portfolio project. Nothing in this repository constitutes investment advice.*
