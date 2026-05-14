# Resume Claims Evidence (Verified Baseline)

This document lists the **minimum, verified claims** that are currently safe to make publicly for this repository.

## Scope
- Baseline verification is limited to local CLI execution and artifact generation for Phase 3 event-panel backtesting.
- This file intentionally avoids claims about production readiness, deployment, alpha persistence, or live trading performance.

## Verified claims
1. The CLI can export the Phase 3 event panel.
   - Command: `python3 -m mini_hedge.cli export-phase3`
   - Input path used by verified runs: `data/exports/phase3_event_panel.csv`

2. The CLI can run a baseline event-panel backtest and write reproducible artifacts.
   - Command: `python3 -m mini_hedge.cli backtest --train-end 2022-12-31`
   - Verified outputs (per run):
     - `trades.csv`, `event_returns.csv`, `daily_returns.csv`, `equity_curve.csv`
     - `summary_metrics.csv`, `split_metrics.csv`, `sensitivity_grid.csv`
     - `equity_curve.png`, `drawdown_curve.png`, `rolling_sharpe.png`, `portfolio_report.md`

3. Baseline metadata is captured for reproducibility.
   - Example keys in `run_metadata.json`: `panel_path`, `config`, `summary_metrics`
   - Verified run metadata files:
     - `data/derived/backtests/20260511T225618Z/run_metadata.json`
     - `data/derived/backtests_smoke/20260511T223809Z/run_metadata.json`

## Evidence policy
- Keep public claims aligned to this list unless new functionality is verified and added here.
- Prefer claim wording that states capabilities and reproducibility over outcome promises.
