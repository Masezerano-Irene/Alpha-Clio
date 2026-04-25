# Project Hedge Notes

## Phase 3 — Sprint 1

Date: 2026-04-25

### Outcome
Sprint 1 is complete and stable enough to move to Sprint 2.

### What was completed
- End-to-end macro event pipeline from ingest to event panel export
- CPI surprise methods fully wired (`naive`, `ema`, `real`)
- NFP and FOMC consensus/probability ingest scaffolding in place
- Phase 3 panel export runs and writes outputs under `data/exports/`
- Notebook reliability fixes applied (`02_derived_signals.ipynb` repaired and validated)
- Path/cwd script reliability fixes applied for IDE runs
- GitHub backup workflow established and used

### Current strengths
- Reproducible data + signal + event workflow
- Multi-model consensus comparison reduces model bias
- Better operational robustness (absolute pathing, dependency fixes, notebook cleanup helper)

### Known weaknesses
- Some event buckets still have low sample counts (decision gate flagged)
- Data quality/coverage depends on external CSV sources and refresh cadence
- Notebook outputs can become unstable if repeatedly saved with heavy outputs

### Sprint 1 artifacts
- Full documentation: `docs/sprint1_documentation_and_sprint2_plan.md`
- Main notebook: `notebooks/02_derived_signals.ipynb`
- Panel export script: `scripts/export_phase3_event_panel.py`
- Notebook repair utility: `scripts/clean_notebooks.py`

### Sprint 2 next steps (saved)
1. Freeze hypotheses, horizons, and decision thresholds.
2. Add inferential layer (bootstrap CI + significance tests).
3. Run robustness splits by regime and surprise magnitude.
4. Produce Sprint 2 artifact tables in `data/exports/`.
5. Record pass/fail decision gate with explicit criteria.
