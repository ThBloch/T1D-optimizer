# T1D Basal Optimizer

Thomas Bloch-Nielsen — T1D diagnosed 2025-04-09.

## Quick start
```
cd D:/claude/t1d/scripts
py -X utf8 basal_analysis.py                          # weekly pattern (research)
py -X utf8 rules_model.py                             # backtest report (research)
py -X utf8 dexcom_fetch.py [--new-pen] [--no-hypo]    # production path: live CGM + dose suggestion
py -X utf8 whoop_api_fetch.py [--full]                # refresh WHOOP JSON cache (incremental by default)
py -X utf8 tests/test_rules.py                        # 38 unittest cases (run from project root)
```
```
/t1d-status                                           # 4-line snapshot: fetch age, clarity date, backlog count, last dose
```

## Structure
```
data/                     Dexcom Clarity CSVs (semicolon, Danish locale)
data/glooko/              Glooko export ZIPs unzipped here; NovoPen bolus lives in `Insulin data/insulin_data_1.csv`
data/whoop_api/           WHOOP raw API responses (cycles/recovery/sleep/workouts.json)
scripts/                  all active analysis code
archive/whoop_csv/        old my_whoop_data_* directories (superseded by API)
archive/scripts_pre_api/  pre-JSON-loader script versions
docs/                     architecture, decisions, progress, superseded files
output/                   generated reports (not committed)
```

## Scripts
- `basal_analysis.py` — main analysis (matching model, weekly pattern, tonight's range)
- `rules_model.py` — Thomas's rules backtest + Decision Tree comparison + tonight's suggestion
- `predictor_test.py`, `ml_model.py`, `bolus_noise_test.py` — secondary analyses
- `inferential_predictor.py` — Phase 5 / R8 analysis: chooses best slope-vs-signals model spec via F-test, computes per-night inferred optimal dose, ranks candidate signals via direct + partial + inferential Spearman with convergence-based tier (HIGH/MED/LOW). Output to `output/inferential_predictor.txt`.
- `strain_binning_analysis.py`, `strain_regression_analysis.py` — Phase A2 strain → slope analyses; the regression module exposes `fit_ols` for reuse.
- `rules.py` — single source of truth for `thomas_rules()`; imported by dexcom_fetch + rules_model. Priority: hypo (-1/-2) overrides; otherwise slope tier (sh_slope vs flat=0.3, mid=0.7, hi=1.2 -> +1/+2/+3 up, -1/-2 down); if slope unavailable falls back to fasting tier (10.0/12.0/14.0). Activity (s1>=12 -> -2u) and new pen (-1u) stack. Clamp [15, 29].
- `dexcom_loader.py` — shared Clarity CSV loader; returns `(glucose_list, basal_list, bolus_by_date)`. Also exposes `load_bolus_events()` (Clarity only) and `load_bolus_combined()` (Clarity pre-cutover + Glooko post-cutover). Warns at load time if any rows fail to parse.
- `novopen_loader.py` — Glooko export loader; `load_glooko_bolus()` returns sorted `[(datetime, units), ...]` of NovoPen 6 injections with Glooko's Prime Detection rule applied (<=2u within 6 min of a following event = prime, dropped).
- `whoop_loader.py` — shared WHOOP loader; reads `data/whoop_api/*.json` → `{date: {strain, recovery, hrv, rhr, sleep_perf}}`
- `dose_diary.py` — read/upsert `data/doses.csv` (one row per dose-night)
- `dexcom_fetch.py` — daily CGM fetch via `pydexcom`; anchors yesterday's dose with **Clarity > diary > prompt** priority; backfills overnight outcome; writes today's suggestion to diary. Flags: `--new-pen` (applies new-pen rule), `--no-hypo` (override CGM-detected hypos as sensor noise).
- `whoop_api_fetch.py` — incremental WHOOP refresh via `whoop-sdk` (4 endpoints, 7-day overlap cursor, dedup-merge by id/cycle_id, 429 backoff). `--full` forces backfill from 2025-04-09. Typical run ~4s.

## Tests
- `tests/test_rules.py` — 38 unittest cases for `thomas_rules` (21 hypo/fasting/activity/pen + 17 slope). Run: `py -X utf8 tests/test_rules.py`

## Data sources (API-driven)
- **Dexcom**: `pydexcom` Share API for live glucose. Creds at `<project_root>/dexcom_creds.json` (plaintext, gitignored). Returns tz-aware local datetimes; `dexcom_fetch.py` strips tzinfo. **Share API has glucose only — no insulin events.** Clarity CSV exports (manual: clarity.dexcom.com → save to `data/`) are the authoritative source for basal/bolus.
- **WHOOP**: official Developer API via `whoop-sdk`. OAuth tokens at `~/.whoop_sdk/config.json`, app credentials at `~/.whoop_sdk/settings.json`. WHOOP CSV exports superseded by JSON cache.

## Key facts
- Run with `py` not `python3` (Windows)
- Paths derive from `__file__` — repo can move directories without code changes
- Dexcom CSV: semicolon-delimited, Danish locale, mmol/L, comma decimals
- Target: fasting 5–8 mmol/L | hypo <4.0 | hyper >10.0
- Bolus sources merged across all dates: Clarity Hurtig rows = manual G7-app entries (regular-pen days); Glooko ACS* rows = NovoPen NFC syncs (smart-pen days). Streams are disjoint by construction (manual G7 never reaches Glooko's pen-source rows; smart-pen events never reach Clarity's raw CSV). Combined via `dexcom_loader.load_bolus_combined()`. Glooko export currently manual; automation pending.
- WHOOP in-progress cycle dating: indexed under start date, so `today_s1` lookup often returns None at dose time — fetch live via API when needed
- WHOOP strain freshness: `score.strain` only updates on WHOOP app sync — check `updated_at`
- Dose diary `data/doses.csv` is gitignored (under `data/`); Clarity-derived dose backfills it automatically when present

## Decisions log
Location: `docs/decisions-log.md`

Format, rules, and when to write: `claude-setup/docs/decisions-log-conventions.md`.

Session protocol:
- Before proposing changes to `thomas_rules`, model parameters, data sources, scripts in `scripts/`, or the analysis approach, read `docs/decisions-log.md`. State which entries are relevant, or explicitly state "no relevant decisions" if none apply.
- If a proposed change contradicts an `accepted` decision (e.g., re-adding s7 as a match variable, removing the hypo-correction exclusion), stop. Either surface the conflict for discussion, or write a superseding entry first.
- Never silently contradict an accepted decision. Never edit a past entry's content - only its `Status` line, and only when superseding.

The `decisions-log-reminder` hookify rule reminds at session end if `scripts/*.py` was edited; non-trivial changes should also produce a new entry in the log.

## Working preferences
- Read `docs/improvements.md` before proposing new refactors.
- Read `docs/code-conventions.md` before adding new scripts, constants, or rule branches - P1-P12 decide where each thing lives.
- Reference file paths instead of pasting file contents.

## Compaction

When compacting, preserve:
- Scripts changed this session and the logic that changed
- Dose rule changes and their reasoning (and whether they were added to decisions-log.md)
- Test results and any failures
- Current blockers and next actions

## Full model context
See memory file or `docs/architecture.md`.
