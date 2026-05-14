<div align="center">

# ⚡ Alpha Clio

### Macro Event Investment Analytics Platform

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Status](https://img.shields.io/badge/Status-Phase%203%20Complete-F0A500?style=for-the-badge)](https://github.com/Masezerano-Irene/Alpha-Clio)
[![Data](https://img.shields.io/badge/Data-FRED%20%7C%20BLS%20%7C%20OANDA%20%7C%20Alpaca-2ECC71?style=for-the-badge)](https://github.com/Masezerano-Irene/Alpha-Clio)
[![License](https://img.shields.io/badge/License-MIT-lightgrey?style=for-the-badge)](https://github.com/Masezerano-Irene/Alpha-Clio)

**[📊 View Live Results Dashboard →](https://masezerano-irene.github.io/Alpha-Clio/)**

*A systematic, rules-based investment analytics platform that models the market impact of US macroeconomic releases across five asset classes*

</div>

---

## 📌 What This Project Does

- Built a Python investment analytics platform to model and evaluate macro-driven investment opportunities; automated ingestion of CPI, NFP, and FOMC release data from FRED and BLS into a structured event panel spanning 2009–2026; engineered return calculations and rolling z-score risk metrics across 365+ macro release observations (NFP: 136, CPI: 216), measuring investment performance outcomes across 1-, 2-, and 5-day windows for three asset classes — US Treasuries, equities, and the dollar index.

- Developed and evaluated z-score-normalized economic surprise signals to predict investment direction; backtested signal performance across 107 discrete investment decisions over 4,454 trading days; identified that next-day return measurement introduced a timing lag that suppressed signal accuracy, quantified the root cause, and redesigned the methodology to a 5-minute intraday event window — documenting all findings, assumptions, and remedial action in structured analytical reports suitable for management review.

---

## 🏆 Key Results

> All numbers from actual backtest runs on real market data (FRED, BLS, Yahoo Finance).

<div align="center">

| Metric | Value |
|:---|:---|
| 📅 Backtest period | February 2009 – March 2026 (4,454 trading days) |
| 🎯 Tradeable signals identified | 107 across full history |
| 📊 Total events analyzed | 365+ macro releases (NFP: 136, CPI: 216, FOMC: 13) |
| 📈 Out-of-sample Sharpe | **0.95** (2023–2026 · 16 events) |
| 💰 Out-of-sample return | **+10%** |
| 📉 Out-of-sample max drawdown | **−2.2%** (vs ≤ 15% threshold) |
| 🛡️ Cost safety margin | **12×** (model: 10 bps · ZT actual: 0.79 bps) |
| 🏛️ Asset classes covered | TLT · EUR/USD · USD/JPY · CL · GC |

</div>

---

## 🔬 Central Methodological Finding

The initial backtest measured returns at **next-day market close** — introducing a 30-hour gap between the 8:30 ET release and the return measurement point. During that window, unrelated market movements swamped the event signal, producing a near-zero Sharpe ratio (0.089).

```
❌ Before:  signal at 08:30 ET → measured at next-day 16:00 ET
            gap = 30 hours of noise → Sharpe 0.089

✅ After:   signal at 08:30 ET → measured at 08:35 ET
            window = 5 minutes of pure signal → OOS Sharpe 0.95
```

Redesigning to a **5-minute intraday window** eliminated the confound. This diagnostic and the methodology correction it produced is the central analytical contribution of Phase 1.

---

## 🏗️ System Architecture

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

## 💼 Portfolio — 5 Instruments, 4 Distinct Factors

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

## 📅 Event Calendar — 13 Events, ~184 Releases/Year

<div align="center">

| Event | Tier | Release ET | Instruments | ~N/yr |
|:---|:---:|:---:|:---|:---:|
| Non-Farm Payrolls | 🔴 1 | 08:30 | TLT · EUR/USD · USD/JPY · CL | 12 |
| CPI | 🔴 1 | 08:30 | TLT · EUR/USD · USD/JPY · GC | 12 |
| FOMC Rate Decision | 🔴 1 | 14:00 | TLT · EUR/USD · USD/JPY · GC | 8 |
| PCE Price Index | 🔴 1 | 08:30 | TLT · EUR/USD · USD/JPY · GC | 12 |
| Initial Jobless Claims | 🟡 2 | 08:30 | TLT · EUR/USD · USD/JPY | 52 |
| ISM Manufacturing PMI | 🟡 2 | 10:00 | EUR/USD · USD/JPY · CL | 12 |
| ISM Services PMI | 🟡 2 | 10:00 | EUR/USD · USD/JPY · CL | 12 |
| Retail Sales | 🟡 2 | 08:30 | TLT · EUR/USD · USD/JPY | 12 |
| PPI | 🟡 2 | 08:30 | TLT · EUR/USD · USD/JPY · GC | 12 |
| Housing Starts | ⚪ 3 | 08:30 | EUR/USD · USD/JPY | 12 |
| Durable Goods | ⚪ 3 | 08:30 | EUR/USD · USD/JPY | 12 |
| Consumer Confidence | ⚪ 3 | 10:00 | EUR/USD · USD/JPY | 12 |
| GDP | ⚪ 3 | 08:30 | EUR/USD · USD/JPY · CL | 4 |

</div>

---

## 🗂️ Project Structure

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
├── index.html                 # 📊 Live results dashboard (GitHub Pages)
└── README.md
```

---

## 📐 Methodology — Step by Step

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

## 🛡️ Execution Cost Model

<div align="center">

| Regime | VIX | Cost (round-trip) | Basis |
|:---|:---:|:---:|:---|
| 🟢 Base | < 20 | **10 bps** | Conservative baseline (12× ZT actual) |
| 🟡 Stress | 25–35 | **15 bps** | Wider spreads in risk-off |
| 🔴 Panic | > 35 | **20 bps** | Liquidity-adjusted |

</div>

**Validation:** Level 2 tick data from 2-year Treasury futures (ZT) showed actual round-trip execution costs of ~0.79 bps during normal conditions — confirming the 10 bps baseline provides a **12× safety margin**.

---

## ✅ Go / No-Go Validation Gate

> No criterion can be waived. Paper trading begins only after all five are met.

<div align="center">

| Criterion | Threshold | OOS Result | Status |
|:---|:---:|:---:|:---:|
| Newey-West Sharpe (holdout) | ≥ 0.50 | **0.95** | ✅ PASS |
| Maximum drawdown (holdout) | ≤ 15% | **−2.2%** | ✅ PASS |
| Stress-period expectancy | ≥ 0 bps | Pending Phase 5 | ⏳ |
| Single-event concentration | ≤ 40% P&L | Pending Phase 5 | ⏳ |
| Signal log completeness | ≥ 95% | Pending Phase 5 | ⏳ |

</div>

---

## 🗺️ Roadmap

- [x] **Phase 0** — Event calendar, signal construction, consensus data collection
- [x] **Phase 1** — Daily backtest, methodology diagnosis, cost model validation
- [x] **Phase 2** — Intraday backtest engine, asymmetric exit system, regime classifier
- [x] **Phase 3** — 5-instrument portfolio, analytics module, factor concentration analysis
- [ ] **Phase 4** — Data collection (Alpaca/OANDA fetch, Bloomberg import)
- [ ] **Phase 5** — Full intraday backtest across all 5 instruments, Go/No-Go gate
- [ ] **Phase 6** — Paper trading on IBKR simulated environment
- [ ] **Phase 7** — Live deployment (post paper-trading validation only)

---

## 🔧 Technologies

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

## 🎓 Academic Context

Developed alongside graduate coursework at **Brandeis University International Business School** (M.S. Business Analytics):

| Course | Grade |
|:---|:---:|
| BUS 294A — Machine Learning for Inflation Event Studies | A |
| FIN 253A — Advanced Quantitative Analysis in Finance | A |
| ECON/FIN 250A — Forecasting in Finance and Economics | A− |
| ECON 213A — Applied Econometrics with R | B+ |
| BUS/FIN 241A — Machine Learning and Data Analysis for Business and Finance | B+ |

---

## 👩‍💻 Author

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
