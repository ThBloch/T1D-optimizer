# T1D Basal Optimizer

Thomas Bloch-Nielsen — T1D diagnosed 2025-04-09.

## Quick start
```
cd D:/claude/t1d/scripts
py -X utf8 basal_analysis.py   # main analysis + tonight's suggestion
py -X utf8 rules_model.py      # rules backtest + tonight's rule-based suggestion
```

## Structure
```
data/      raw Dexcom CSVs + WHOOP folders — drop new exports here
scripts/   all active analysis code
docs/      architecture, decisions, progress, superseded files
output/    generated reports (not committed)
```

## Key facts
- Run with `py` not `python3` (Windows)
- Dexcom CSV: semicolon-delimited, Danish locale, mmol/L, comma decimals
- Target: fasting 5–8 mmol/L | hypo <4.0 | hyper >10.0
- Bolus logging gap: from 2026-01-31 (switched to NovoPen 6 — data not yet exported)

## Do not use
`docs/analyze.py`, `docs/recalibrate.py`, `docs/REFERENCE.md` — all superseded.

## Full model context
See memory file or `docs/architecture.md`.
