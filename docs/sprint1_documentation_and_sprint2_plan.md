# Sprint 1 Documentation and Sprint 2 Plan

## Scope of This Document
This document captures:
- What was completed in Sprint 1 (data + signal pipeline stabilization)
- Current strengths and weaknesses
- Risks and mitigation actions
- A concrete Sprint 2 execution plan with acceptance criteria

Date: 2026-04-25  
Project: `Mini_Hedge`

---

## Sprint 1 Objective (What This Step Was About)
Sprint 1 focused on building a reliable end-to-end macro event pipeline:
- Ingest and store core macro series in SQLite
- Build derived signals (MoM, YoY, z-score, surprise)
- Map macro events to market reactions (bond/yield windows)
- Export a consolidated Phase 3 event panel
- Keep notebooks and scripts runnable in local IDE workflows

Primary goal: move from ad-hoc analysis to a repeatable baseline suitable for formal testing in Sprint 2.

---

## What Was Implemented in Sprint 1

## 1) Data and Storage Layer
- Local DB (`data/econ.db`) populated with core macro series:
  - `CUUR0000SA0`, `CPILFESL`, `FEDFUNDS`, `DGS10`, `T10Y2Y`, `UNRATE` (+ `CPIAUCSL` in storage)
- CSV pipelines added/maintained for event expectations:
  - CPI consensus (`data/cpi_consensus.csv`)
  - NFP consensus/release calendar (`data/nfp_consensus.csv`, `data/nfp_release_calendar.csv`)
  - FOMC consensus/probabilities (`data/fomc_consensus.csv`, `data/fomc_probabilities.csv`)
  - FOMC probabilities history from MPT workbook (`data/fomc_probabilities_history.csv`)

## 2) Signal Construction
- CPI surprise methods supported and compared:
  - `naive`, `ema`, `real`
- Directional signal generated from surprise thresholding
- Surprise z-score support added for magnitude context
- Real-consensus method integrated into reporting and comparison output

## 3) Event Reaction Layer
- Event windows and return/yield reactions implemented for:
  - 1D, 3D, 5D horizons
- Window completeness flags present to avoid false loss counting from incomplete windows
- Phase 3 panel exporter implemented and validated:
  - `scripts/export_phase3_event_panel.py`
  - outputs to `data/exports/phase3_event_panel.csv` (+ optional parquet)

## 4) Reliability/DevEx Fixes
- Path resolution fixes in scripts to avoid working-directory breakage:
  - scripts now anchor data paths to repo root
- Dependency fixes:
  - `openpyxl` for `.xlsx` ingestion
  - `pyarrow` optional for parquet path
- Notebook resiliency:
  - `02_derived_signals.ipynb` repaired and validated
  - malformed output corruption mitigated by output-stripping workflow
  - `scripts/clean_notebooks.py` added for schema-safe cleanup

## 5) Version Control Hygiene
- Sensitive/local artifacts ignored (`.env`, DB files, `.claude`, etc.)
- Regenerated outputs excluded from tracking (`data/exports/`)
- Large downloaded workbook excluded (`data/mpt_histdata.xlsx`)
- Incremental GitHub pushes completed successfully

---

## Sprint 1 Validation Snapshot
Latest observed checks (project-local):
- Snapshot table runs and returns 6/6 indicators without errors
- `yield_around_releases()` returns 218 events with expected horizon columns
- `compare_consensus_methods()` produces all 3 methods (NAIVE/EMA/REAL)
- Consensus CSV integrity checks pass (no duplicate dates in current CPI consensus file)
- `export_phase3_event_panel.py` runs end-to-end and writes panel + metadata
- `02_derived_signals.ipynb` executes through all cells after repair

Note: metric values (win rate, counts) are method- and data-snapshot-dependent and may change as source CSVs refresh.

---

## Strengths (What Is Working Well)
- **End-to-end pipeline exists**: ingest -> signal -> event mapping -> export -> notebook analysis
- **Multiple expectation models**: naive/EMA/real comparison reduces model-blind conclusions
- **Operational resiliency improved**: path anchoring removes IDE cwd errors
- **Reproducibility improved**: scripts and notebook behavior are now deterministic enough for reruns
- **Clear transition point to formal testing**: Sprint 2 can focus on statistical rigor instead of plumbing

---

## Weaknesses / Gaps (What Still Needs Attention)
- **Data dependency quality varies by source**
  - Some files are scraped snapshots, not full vendor-grade history
  - Refresh cadence and schema drift risk remain
- **Notebook fragility risk still exists**
  - Jupyter outputs can become malformed across tools if not cleaned regularly
- **Signal interpretation remains descriptive**
  - Current outputs provide strong diagnostics but not full inferential confidence
- **Sample imbalance by bucket**
  - Some sign/magnitude buckets have low `n` (already visible in decision-gate output)
- **Mixed granularity constraints**
  - Event dates, release calendars, and market trading calendars need careful alignment checks in all splits

---

## Key Risks and Mitigations
- **Risk: source CSV format changes**
  - Mitigation: strict column validation in ingest scripts + explicit error messages
- **Risk: notebook “corrupted” errors recur**
  - Mitigation: run `python scripts/clean_notebooks.py` before commit/push
- **Risk: overfitting from repeated slicing**
  - Mitigation: pre-register Sprint 2 hypotheses and gate metrics before exploratory cuts
- **Risk: confusing method-specific win rates**
  - Mitigation: report all metrics with explicit method tags (NAIVE/EMA/REAL)

---

## Sprint 1 Exit Criteria (Status)
- Data pipeline operational: **Met**
- Signal pipeline operational: **Met**
- Event panel export operational: **Met**
- Notebook execution baseline stable: **Met (with cleanup utility in place)**
- GitHub backup workflow stable: **Met**

Conclusion: **Ready to proceed to Sprint 2**.

---

## Sprint 2 Objective
Convert Sprint 1 descriptive outputs into a formal, testable event-study package with clear decision rules.

---

## Sprint 2 Work Plan

## Phase A — Statistical Core
1. Define frozen hypotheses by event type and instrument:
   - Expected sign and relative effect by horizon
2. Add inference layer:
   - Mean/median effect
   - Bootstrap confidence intervals
   - Parametric and/or permutation significance checks
3. Standardize result tables:
   - One artifact per event type/horizon/model with consistent schema

## Phase B — Robustness and Segmentation
1. Regime segmentation:
   - Hiking vs cutting vs neutral periods
2. Magnitude segmentation:
   - Surprise z-score bins with minimum sample thresholds
3. Model robustness:
   - Compare NAIVE vs EMA vs REAL under same window definitions

## Phase C — Decision Gate and Reporting
1. Define pass/fail thresholds before reading outputs:
   - Minimum `n` per key cell
   - Minimum consistency across horizons
   - Significance confidence threshold
2. Produce Sprint 2 summary artifact:
   - Methods, assumptions, key findings, limitations, next actions

---

## Sprint 2 Deliverables
- `data/exports/sprint2_*` result tables (CSV/optional parquet)
- Reproducible runner script for Sprint 2 calculations
- Updated notebook/report section with:
  - methodology
  - significance interpretation
  - decision outcome
- Clear “go/no-go” statement for advancing strategy prototyping

---

## Suggested Immediate Next Commands
From repo root:

```bash
python scripts/export_phase3_event_panel.py
python scripts/clean_notebooks.py notebooks/02_derived_signals.ipynb
```

Then begin Sprint 2 branch/workstream with a frozen parameter set for horizons, buckets, and thresholds.

---

## Practical Rule for Future Stability
Before every push:
1. Rebuild panel/export artifacts as needed
2. Clean notebooks (`scripts/clean_notebooks.py`)
3. Re-run critical notebook/script smoke tests
4. Commit only source + required small data, avoid regenerated outputs/large binaries

