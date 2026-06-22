# T1D Basal Optimizer

Thomas Bloch-Nielsen — T1D diagnosed 2025-04-09.

## Quick start
```
cd D:/claude/t1d/scripts
py -X utf8 basal_analysis.py                          # weekly pattern (research)
py -X utf8 rules_model.py                             # backtest report (research)
py -X utf8 dexcom_events_fetch.py [--full]            # refresh Dexcom API cache (incremental by default; run before dexcom_fetch.py)
py -X utf8 dexcom_fetch.py [--dose N] [--strain N] [--new-pen] [--no-hypo]    # production path: live CGM + dose suggestion
py -X utf8 whoop_api_fetch.py [--full]                # refresh WHOOP JSON cache (incremental by default)
py -X utf8 tests/test_rules.py                        # 38 unittest cases (run from project root)
```
```
/t1d-status                                           # 4-line snapshot: fetch age, clarity date, backlog count, last dose
/session-done                                         # append session-log entry, run tests, commit + push (with approval gate)
```

## Structure
```
data/                     Dexcom Clarity CSVs (semicolon, Danish locale)
data/dexcom_api/          Dexcom Developer API cache (events.json + egvs.json; gitignored)
data/glooko/              Glooko export ZIPs unzipped here; NovoPen bolus lives in `Insulin data/insulin_data_1.csv`
data/whoop_api/           WHOOP raw API responses (cycles/recovery/sleep/workouts.json)
scripts/                  all active analysis code
archive/whoop_csv/        old my_whoop_data_* directories (superseded by API)
archive/scripts_pre_api/  pre-JSON-loader script versions
docs/                     architecture, decisions, progress, superseded files
output/                   generated reports (not committed)
```

## Scripts
- `basal_analysis.py` — weekly pattern (research): matching model, comparable-night stats, regression appendix
- `rules_model.py` — backtest report (research): Thomas's rules backtest + Decision Tree comparison
- `predictor_test.py`, `ml_model.py`, `bolus_noise_test.py` — secondary analyses
- `inferential_predictor.py` — Phase 5 / R8 analysis: chooses best slope-vs-signals model spec via F-test, computes per-night inferred optimal dose, ranks candidate signals via direct + partial + inferential Spearman with convergence-based tier (HIGH/MED/LOW). Output to `output/inferential_predictor.txt`.
- `strain_binning_analysis.py`, `strain_regression_analysis.py` — Phase A2 strain → slope analyses; the regression module exposes `fit_ols` for reuse.
- `rules.py` — single source of truth for `thomas_rules()`; imported by dexcom_fetch + rules_model. Priority: hypo (-1/-2) overrides; otherwise slope tier (sh_slope vs flat=0.3, mid=0.7, hi=1.2 -> +1/+2/+3 up, -1/-2 down); if slope unavailable falls back to fasting tier (10.0/12.0/14.0). Activity (s1>=12 -> -2u) and new pen (-1u) stack. Clamp [15, 29].
- `dexcom_events_fetch.py` — incremental Dexcom Developer API v3 fetcher; writes `data/dexcom_api/events.json` (insulin events) and `egvs.json` (EGV glucose). Auth via OAuth tokens in `~/.dexcom_api/`. `--full` seeds events from diagnosis + egvs last 30 days. Run before `dexcom_fetch.py`.
- `dexcom_events_loader.py` — offline loader for the API cache; exposes `load_api_basal()`, `load_api_bolus()`, `load_api_glucose(start, end)`. Converts mg/dL -> mmol/L, strips tz offsets, filters deleted events.
- `dexcom_loader.py` — shared Clarity CSV loader; returns `(glucose_list, basal_list, bolus_by_date)`. Also exposes `load_bolus_events()` (Clarity only) and `load_bolus_combined()` (API fastActing from cutover date + Clarity Hurtig before cutover + Glooko always). Warns at load time if any rows fail to parse.
- `novopen_loader.py` — Glooko export loader; `load_glooko_bolus()` returns sorted `[(datetime, units), ...]` of NovoPen 6 injections. Delegates Prime Detection to `bolus_classification.filter_primes()`.
- `bolus_classification.py` — Glooko Prime Detection rule (`filter_primes`, `PRIME_MAX_U=2.0`, `PRIME_WINDOW=6 min`). Single source of truth; imported by `novopen_loader`.
- `whoop_cycles.py` — WHOOP cycle-to-local-date mapping (`cycle_date_for`: end-6h for closed cycles, start for in-progress). Imported by `whoop_loader`.
- `whoop_loader.py` — shared WHOOP loader; reads `data/whoop_api/*.json` → `{date: {strain, recovery, hrv, rhr, sleep_perf}}`
- `dose_diary.py` — read/upsert `data/doses.csv` (one row per dose-night)
- `dexcom_fetch.py` — daily CGM fetch; live reading via `pydexcom` Share API; overnight window from Developer API cache (`load_api_glucose`). Anchors yesterday's dose with **API > Clarity > diary > flag** priority. Backfills overnight outcome; writes today's suggestion to diary. Refuses to suggest when WHOOP strain unavailable (emits `NEEDS: strain`). Flags: `--dose N`, `--strain N`, `--new-pen`, `--no-hypo`.
- `whoop_api_fetch.py` — incremental WHOOP refresh via `whoop-sdk` (4 endpoints, 7-day overlap cursor, dedup-merge by id/cycle_id, 429 backoff). `--full` forces backfill from 2025-04-09. Typical run ~4s.

## Tests
- `tests/test_rules.py` — 38 unittest cases for `thomas_rules` (21 hypo/fasting/activity/pen + 17 slope). Run: `py -X utf8 tests/test_rules.py`
- `tests/test_night_stats.py` - 29 unittest cases for `night_stats()` + `second_half_trend()` + `overnight_window()` (slope direction/magnitude, degenerate/insufficient inputs, hypo-event counting, hypo-correction boundaries, TIR fields, overnight-window boundary inclusivity at 06:20 + month-end crossing). Run: `py -X utf8 tests/test_night_stats.py`
- `tests/test_bolus_classification.py` — 15 unittest cases for `filter_primes` (8: boundaries at `PRIME_MAX_U` and `PRIME_WINDOW`, bidirectional lookahead, empty input) and `find_minute_unit_overlaps` (7: empty inputs, exact-minute matches, unit/minute mismatches, second-level skew within same minute, minute-boundary). Run: `py -X utf8 tests/test_bolus_classification.py`
- `tests/test_dexcom_events_loader.py` — 22 unittest cases for `dexcom_events_loader` (4 tz-strip, 8 basal: deleted/updated/same-day-sum/sort, 4 bolus: fast-only/deleted/sort, 6 glucose: mg/dL conversion, window filter, sort). Run: `py -X utf8 tests/test_dexcom_events_loader.py`

## Data sources (API-driven)
- **Dexcom Developer API v3**: authoritative for basal (longActing) + bolus (fastActing, regular-pen era) + overnight EGV glucose. OAuth credentials at `~/.dexcom_api/` (config.json + tokens.json). EU server: `api.dexcom.eu`. Cache at `data/dexcom_api/` (gitignored). 3h EU data delay is irrelevant for the overnight window (already in the past at dose time). Refresh with `dexcom_events_fetch.py`.
- **Dexcom Share API**: `pydexcom`, live glucose reading only (real-time, no delay). Creds at `<project_root>/dexcom_creds.json` (gitignored). **Share API has glucose only — no insulin events.** Clarity CSV exports (manual: clarity.dexcom.com -> save to `data/`) are the fallback for basal/bolus when API cache is absent or stale.
- **WHOOP**: official Developer API via `whoop-sdk`. OAuth tokens at `~/.whoop_sdk/config.json`, app credentials at `~/.whoop_sdk/settings.json`. WHOOP CSV exports superseded by JSON cache.

## Key facts
- Run with `py` not `python3` (Windows)
- Paths derive from `__file__` — repo can move directories without code changes
- Dexcom CSV: semicolon-delimited, Danish locale, mmol/L, comma decimals
- Target: fasting 5–8 mmol/L | hypo <4.0 | hyper >10.0
- Bolus sources merged: API fastActing (authoritative from 2025-04-26, earliest API coverage) + Clarity Hurtig (pre-API dates only) + Glooko ACS* rows (NovoPen NFC syncs, always disjoint). Combined via `dexcom_loader.load_bolus_combined()`. Glooko export currently manual; automation pending.
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
- Global ASCII rule (C:\Users\thblo\.claude\CLAUDE.md section 3) applies to all files in this repo - docs, code, and commands. Use hyphen not em-dash, straight quotes not curly, ASCII arrows (->) not Unicode, etc. Exceptions: Danish data strings that must match CSV content (Høj, Lav, field names) are never touched.

## Compaction

When compacting, preserve:
- Scripts changed this session and the logic that changed
- Dose rule changes and their reasoning (and whether they were added to decisions-log.md)
- Test results and any failures
- Current blockers and next actions

## Full model context
See memory file or `docs/architecture.md`.
