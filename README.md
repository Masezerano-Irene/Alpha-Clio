<div align="center">

# Alpha Clio

### Macro Event Investment Analytics Platform

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Status](https://img.shields.io/badge/Status-Active%20Research-F0A500?style=for-the-badge)](https://github.com/Masezerano-Irene/Alpha-Clio)
[![Data](https://img.shields.io/badge/Data-FRED%20%7C%20BLS%20%7C%20OANDA%20%7C%20Alpaca-2ECC71?style=for-the-badge)](https://github.com/Masezerano-Irene/Alpha-Clio)
[![Phase](https://img.shields.io/badge/Phase-3%20of%207%20Complete-58A6FF?style=for-the-badge)](https://github.com/Masezerano-Irene/Alpha-Clio)

**[View Live Results Dashboard →](https://masezerano-irene.github.io/Alpha-Clio/)**

*A systematic, rules-based investment analytics platform that models and evaluates the market impact of US macroeconomic surprises across five asset classes — built as a quantitative research portfolio piece and behavioral-finance discipline framework.*

</div>

---

## What This Project Does

- Built a Python investment analytics platform to model and evaluate macro-driven investment opportunities; automated ingestion of CPI, NFP, and FOMC release data from FRED and BLS into a structured event panel spanning 2009–2026; engineered return calculations and rolling z-score risk metrics across 365+ macro release observations (NFP: 136, CPI: 216), measuring investment performance outcomes across 1-, 2-, and 5-day windows for three asset classes — US Treasuries, equities, and the dollar index.

- Developed and evaluated z-score-normalized economic surprise signals to predict investment direction; backtested signal performance across 107 discrete investment decisions over 4,454 trading days; identified that next-day return measurement introduced a timing lag that suppressed signal accuracy, quantified the root cause, and redesigned the methodology to a 5-minute intraday event window — documenting all findings, assumptions, and remedial action in structured analytical reports suitable for management review.

- Designed and implemented a multi-source data pipeline integrating FRED, BLS, OANDA, Alpaca Markets, and Bloomberg CSV exports into a unified SQLite and Parquet store; built modular fetchers for FX tick data (EUR/USD, USD/JPY), Treasury ETF bars, and futures price series — normalizing heterogeneous data across varying release frequencies, timezone conventions, and data quality gaps to produce a consistent, reproducible event panel.

- Constructed a 3-tier signal classification system across 13 macroeconomic event types, mapping each release to its most sensitive instruments based on economic transmission logic; engineered expanding-window z-score normalization with no lookahead bias, directional hypothesis encoding, and a position sizing framework that scales signal conviction to trade size — translating economic data deviations into structured investment decisions across TLT, EUR/USD, USD/JPY, Crude Oil, and Gold.

- Built a VIX-based market regime classifier with instrument-specific position size multipliers; defined four regime states (Normal / Elevated / Stress / Panic) based on prior-day VIX levels and assigned asymmetric scaling rules to each instrument — including carry-trade amplification for USD/JPY in stress environments and safe-haven holds for TLT and Gold in panic — ensuring the risk framework responds systematically to volatility regimes without introducing discretionary judgment.

- Engineered a 5-minute intraday event window backtest engine with a 2D parameter grid search across exit horizons (3, 5, 7, 10, 15 minutes) and z-score thresholds; implemented a locked 20% holdout with Newey-West HAC-adjusted t-statistics and block bootstrap confidence intervals to validate signal performance under autocorrelation-robust conditions — producing statistically rigorous out-of-sample attribution separated from in-sample optimization.

- Developed a performance attribution and analytics module decomposing signal hit rate, gross return, and expectancy by instrument, event tier, z-score bucket, and VIX regime; added cross-instrument basis risk analysis (co-hit rates and conflicting signal detection), PCA-based factor concentration scoring to quantify portfolio diversification, and a five-criterion Go/No-Go gate to govern the transition from backtesting to paper trading.

- Validated the execution cost model against Level 2 tick data from 2-year Treasury futures (ZT); quantified actual round-trip execution costs at ~0.79 bps under normal market conditions, establishing a 12× safety margin against the 10 bps model baseline; extended cost assumptions to 15 bps and 20 bps for stress and panic regimes respectively to account for wider spreads and liquidity deterioration during risk-off environments.

---

## Key Results

> All numbers are from actual backtest runs on real market data (FRED, BLS, Yahoo Finance). Results should be interpreted in the context of current limitations documented in the Research Challenges section below.

<div align="center">

| Metric | Value |
|:---|:---|
| Backtest period | February 2009 – March 2026 (4,454 trading days) |
| Tradeable signals identified | 107 across full history |
| Total events analyzed | 365+ macro releases (NFP: 136, CPI: 216, FOMC: 13) |
| Out-of-sample Sharpe | **0.95** (2023–2026 · 16 events) |
| Out-of-sample return | **+10%** |
| Out-of-sample max drawdown | **−2.2%** (vs ≤ 15% threshold) |
| Cost safety margin | **12×** (model: 10 bps · ZT actual: 0.79 bps) |
| Asset classes covered | TLT · EUR/USD · USD/JPY · CL · GC |

</div>

---

## Central Methodological Finding

The initial backtest measured returns at **next-day market close** — introducing a 30-hour gap between the 8:30 ET release and the return measurement point. During that window, unrelated market movements swamped the event signal, producing a near-zero Sharpe ratio (0.089).

```
Before:  signal at 08:30 ET → measured at next-day 16:00 ET
         gap = 30 hours of noise → Sharpe 0.089

After:   signal at 08:30 ET → measured at 08:35 ET
         window = 5 minutes of pure signal → OOS Sharpe 0.95
```

Redesigning to a **5-minute intraday window** eliminated the confound. This diagnostic finding, and the methodology correction it produced, is the central analytical contribution of Phase 1.

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
│                       EXIT LAYER                                │
│  Rule 1 — Hard Stop  : −2 bps within first 30 seconds          │
│  Rule 2 — HWM Trail  : 60% giveback from peak (if peak ≥ 1.5)  │
│  Rule 3 — Time Exit  : horizons tested: 3/5/7/10/15 min        │
│  (270s cap for FOMC — exits before press conference begins)     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ANALYTICS LAYER                              │
│  • Signal accuracy (hit rate by tier / instrument / regime)     │
│  • Cross-instrument correlation & factor concentration (PCA)    │
│  • Basis risk: co-hit rate and conflicting signal detection      │
│  • Performance attribution: expected vs actual by event type    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Portfolio — 5 Instruments, 4 Distinct Factors

<div align="center">

| Instrument | Asset | Primary Factor | Regime Behaviour |
|:---:|:---|:---|:---|
| ![TLT](https://img.shields.io/badge/TLT-20yr%20Treasury-0066CC?style=flat-square) | 20-yr Treasury ETF | Nominal rates / duration | Safe-haven in panic — holds 100% |
| ![EURUSD](https://img.shields.io/badge/EUR%2FUSD-FX-6B48FF?style=flat-square) | Euro / Dollar FX | Dollar strength signal | Reduced to 50% in panic |
| ![USDJPY](https://img.shields.io/badge/USD%2FJPY-FX%20Carry-9B59B6?style=flat-square) | Dollar / Yen FX | Dollar + JPY carry hedge | 150% in stress; paused in panic |
| ![CL](https://img.shields.io/badge/CL-Crude%20Oil-FF6B35?style=flat-square) | Crude Oil Futures | Energy / global growth | Paused in panic (demand collapse) |
| ![GC](https://img.shields.io/badge/GC-Gold-F0A500?style=flat-square) | Gold Futures | Real rates / inflation hedge | Safe-haven in panic — holds 100% |

</div>

> **Design note:** EUR/USD and USD/JPY may appear redundant as both FX pairs respond to the dollar. USD/JPY was retained for its unique carry-trade component: in stress regimes (VIX 25–35), JPY strengthens independently of the macro surprise signal due to carry unwind, providing conditional diversification precisely when the TLT position is most at risk.

---

## Event Calendar — 13 Events, ~184 Releases/Year

<div align="center">

| Event | Tier | Release ET | Instruments | ~N/yr |
|:---|:---:|:---:|:---|:---:|
| Non-Farm Payrolls | 1 | 08:30 | TLT · EUR/USD · USD/JPY · CL | 12 |
| CPI | 1 | 08:30 | TLT · EUR/USD · USD/JPY · GC | 12 |
| FOMC Rate Decision | 1 | 14:00 | TLT · EUR/USD · USD/JPY · GC | 8 |
| PCE Price Index | 1 | 08:30 | TLT · EUR/USD · USD/JPY · GC | 12 |
| Initial Jobless Claims | 2 | 08:30 | TLT · EUR/USD · USD/JPY | 52 |
| ISM Manufacturing PMI | 2 | 10:00 | EUR/USD · USD/JPY · CL | 12 |
| ISM Services PMI | 2 | 10:00 | EUR/USD · USD/JPY · CL | 12 |
| Retail Sales | 2 | 08:30 | TLT · EUR/USD · USD/JPY | 12 |
| PPI | 2 | 08:30 | TLT · EUR/USD · USD/JPY · GC | 12 |
| Housing Starts | 3 | 08:30 | EUR/USD · USD/JPY | 12 |
| Durable Goods | 3 | 08:30 | EUR/USD · USD/JPY | 12 |
| Consumer Confidence | 3 | 10:00 | EUR/USD · USD/JPY | 12 |
| GDP | 3 | 08:30 | EUR/USD · USD/JPY · CL | 4 |

</div>

---

## Go / No-Go Validation Gate

> No criterion can be waived. Paper trading begins only after all five are met.

<div align="center">

| Criterion | Threshold | OOS Result | Status |
|:---|:---:|:---:|:---:|
| Newey-West Sharpe (holdout) | ≥ 0.50 | **0.95** | PASS |
| Maximum drawdown (holdout) | ≤ 15% | **−2.2%** | PASS |
| Stress-period expectancy | ≥ 0 bps | Pending Phase 5 | Pending |
| Single-event concentration | ≤ 40% P&L | Pending Phase 5 | Pending |
| Signal log completeness | ≥ 95% | Pending Phase 5 | Pending |

</div>

---

## Project Status — What Is Built and What Comes Next

This project is under active research and development. Phases 0 through 3 are complete. The system architecture, signal logic, regime framework, exit rules, analytics module, and cost model are all implemented and tested on a single-instrument baseline (TLT × CPI events). Full multi-instrument intraday backtesting has not yet been run — that is the focus of Phases 4 and 5.

**What is complete:**
- Event calendar with 13 events, 3-tier z-score classification, and instrument-event mapping across 5 asset classes
- VIX regime classifier with per-instrument position size multipliers and asymmetric panic/stress rules
- Three-rule exit system (hard stop, high-watermark trail, time exit) with multi-horizon parameter grid
- Analytics module: signal accuracy, basis risk, cross-instrument correlation, PCA factor concentration
- Time-dependent execution cost model validated against Level 2 Treasury futures tick data
- Baseline backtest on TLT × CPI events confirming the 5-minute intraday window methodology

**What comes next:**
- Phase 4 — Collect intraday FX data (OANDA), equity data (Alpaca), and historical futures data (Bloomberg import); build the unified data loader across all five instruments
- Phase 5 — Run the full 5-instrument intraday backtest across all 13 event types; complete the Go/No-Go gate; optimize exit horizons and z-score thresholds via 2D parameter grid
- Phase 6 — Paper trading on IBKR simulated environment; monitor live signal generation against actual releases; track slippage versus the cost model
- Phase 7 — Live deployment, only after paper trading produces results that confirm the backtest is not overfitted

The dashboard at [masezerano-irene.github.io/Alpha-Clio](https://masezerano-irene.github.io/Alpha-Clio/) will be updated as each phase is completed.

---

## Research Challenges and Open Questions

The following are genuine methodological limitations currently under investigation. None of the approaches below are final — all alternatives are still being evaluated.

**1. Historical consensus data quality**
The backtest relies on consensus forecasts (the "expected" figure that economic surprises are measured against). Data quality from public sources such as ForexFactory is uncertain before 2012, which may introduce noise into the surprise signal for the earlier part of the backtest period. The alternative under consideration is sourcing historical consensus from Bloomberg (available through university access) or a paid provider such as FactSet or Refinitiv Eikon, which maintain cleaner panel data going back to the early 2000s. This is not resolved.

**2. FOMC surprise construction**
Measuring the FOMC surprise — how much the rate decision deviated from market expectations — requires OIS-implied rate path data, which is not freely available. The current implementation uses a simplified consensus approach that does not fully capture intraday repricing of the rate path. Alternatives under research include using fed funds futures implied rates from CME Group data, or restricting FOMC events to scheduled meetings where a clear consensus rate change was forecasted.

**3. Continuous futures contract construction**
Crude oil (CL) and gold (GC) are futures contracts that expire and roll. Building a clean historical price series requires a roll methodology — the two most common are ratio adjustment (backward-adjusting all prices when a contract rolls) and the Panama method (forward-filling from the front contract). Neither perfectly preserves return distributions. This has not been implemented for the intraday backtest yet, and the choice of roll method can meaningfully affect backtest results on futures instruments.

**4. Limited trade count on commodity instruments**
CL and GC are mapped to Tier 1–2 events only, producing approximately 40–44 trades per year. Across the full backtest period this gives a manageable sample, but when broken into subperiods or regime slices the per-cell count drops significantly, reducing the statistical power of attribution analysis. The alternative under research is lowering the z-score threshold for these instruments to increase trade frequency, but this risks including weaker signals. This tradeoff has not been resolved.

**5. Training period underperformance**
The in-sample (training) Sharpe is −0.085, meaning the strategy lost money during the 2009–2022 training period. The out-of-sample period (2023–2026, 16 events) produced a 0.95 Sharpe and +10% return — but 16 events is a small sample and may not be representative. It is possible the training losses reflect genuine regime changes in macro-market relationships over that period, or that the current signal parameters are not well-calibrated to the full history. Walk-forward validation (rolling train windows) is under consideration as an alternative to the single 80/20 split, but has not been implemented.

**6. Intraday data coverage gaps**
Alpaca Markets provides equity data (TLT) from 2016 onward. OANDA provides FX data (EUR/USD, USD/JPY) from 2005 onward. Bloomberg CSV exports cover historical futures (CL, GC) prior to IBKR accumulation. The period 2009–2016 has incomplete intraday coverage for some instruments, which means the full-history intraday backtest will need to handle missing data periods differently depending on the instrument. The approach for bridging these gaps — imputation, exclusion, or instrument-specific backtest windows — has not been finalized.

---

## Methodology — Step by Step

### Step 1 — Surprise Signal Construction
Economic surprises are normalised using z-scores:

```
surprise_z = (actual_release − consensus_forecast) / std(historical_surprises)
```

The standard deviation is computed over all prior releases for that event type using an expanding window to avoid lookahead bias.

### Step 2 — Signal Filtering by Tier
Only events where `|surprise_z|` exceeds the tier threshold are traded:
- **Tier 1:** `|z| ≥ 0.8` — large, high-conviction surprises
- **Tier 2:** `|z| ≥ 1.2` — medium surprises with supporting conditions
- **Tier 3:** `|z| ≥ 1.5` — only the largest surprises on lower-impact events

### Step 3 — Regime Assessment
Prior-day VIX close classifies the market regime before any trade is opened. The regime layer **never creates or cancels a trade** — it only scales position sizes already authorised by the signal layer.

### Step 4 — Entry and Exit
Entry is placed at the 8:30 ET open bar (or 14:00 for FOMC). Three exit rules run simultaneously on every 1-minute bar:
1. Hard stop if loss exceeds 2 bps in first 30 seconds
2. Trail exit if trade retraces 60% from its peak gain
3. Time exit tested across five horizons: 3, 5, 7, 10, and 15 minutes (270s cap for FOMC, before the press conference)

### Step 5 — Attribution and Validation
Every trade is attributed by: instrument, event type, tier, z-score bucket, and VIX regime. Validation uses a locked 20% holdout with Newey-West adjusted t-statistics and block bootstrap confidence intervals for Sharpe ratio.

---

## Roadmap

- [x] **Phase 0** — Event calendar, signal construction, consensus data collection
- [x] **Phase 1** — Daily backtest, timing lag diagnosis, cost model validation (ZT tick data)
- [x] **Phase 2** — Intraday backtest engine, asymmetric exit system, regime classifier
- [x] **Phase 3** — 5-instrument portfolio, analytics module, factor concentration (PCA)
- [ ] **Phase 4** — Data collection: Alpaca/OANDA intraday fetch, Bloomberg historical import
- [ ] **Phase 5** — Full 5-instrument intraday backtest across all 13 event types, Go/No-Go gate
- [ ] **Phase 6** — Paper trading on IBKR simulated environment
- [ ] **Phase 7** — Live deployment, post paper-trading validation only

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
├── notebooks/
│   ├── 02_derived_signals.ipynb
│   └── 03_market_reactions.ipynb
├── scripts/
│   └── econ.ipynb
├── index.html                 # Live results dashboard (GitHub Pages)
└── README.md
```

---

## Execution Cost Model

<div align="center">

| Regime | VIX | Cost (round-trip) | Basis |
|:---|:---:|:---:|:---|
| Base | < 20 | **10 bps** | Conservative baseline (12× ZT actual) |
| Stress | 25–35 | **15 bps** | Wider spreads in risk-off |
| Panic | > 35 | **20 bps** | Liquidity-adjusted |

</div>

**Validation:** Level 2 tick data from 2-year Treasury futures (ZT) showed actual round-trip execution costs of ~0.79 bps during normal conditions — confirming the 10 bps baseline provides a **12× safety margin**.

---

## Technologies

<div align="center">

| Category | Tools |
|:---|:---|
| Language | ![Python](https://img.shields.io/badge/Python_3.11+-3776AB?style=flat-square&logo=python&logoColor=white) |
| Data manipulation | `pandas` · `numpy` · `pyarrow` |
| Market data | `alpaca-py` · `oandapyV20` · `ib_insync` · `yfinance` |
| Storage | SQLite · Parquet |
| Visualisation | `matplotlib` (Agg backend — headless) |
| Statistics | `scipy` · `statsmodels` (Newey-West) |
| Version control | Git / GitHub |

</div>

---

## Academic Context

Developed alongside graduate coursework at **Brandeis University International Business School** (M.S. Business Analytics):

| Course | Grade |
|:---|:---:|
| BUS 294A — Machine Learning for Inflation Event Studies | A |
| FIN 253A — Advanced Quantitative Analysis in Finance | A |
| ECON/FIN 250A — Forecasting in Finance and Economics | A− |
| ECON 213A — Applied Econometrics with R | B+ |
| BUS/FIN 241A — Machine Learning and Data Analysis for Business and Finance | B+ |

---

## Author

<div align="center">

**Irene Masezerano**
M.S. Business Analytics — Brandeis University (May 2026)

[![Email](https://img.shields.io/badge/Email-masezirene%40gmail.com-EA4335?style=for-the-badge&logo=gmail&logoColor=white)](mailto:masezirene@gmail.com)
[![GitHub](https://img.shields.io/badge/GitHub-Masezerano--Irene-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/Masezerano-Irene)
[![Dashboard](https://img.shields.io/badge/Live%20Dashboard-View%20Results-58A6FF?style=for-the-badge)](https://masezerano-irene.github.io/Alpha-Clio/)

</div>

---

<div align="center">
<sub>Alpha Clio is a research and portfolio project. Nothing in this repository constitutes investment advice.</sub>
</div>
