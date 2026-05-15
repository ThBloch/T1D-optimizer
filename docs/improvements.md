# Improvement Backlog

Generated 2026-05-15 from architecture critique. Read this before proposing new refactors.

## A. Token saving (priority)

- [x] Add "Working preferences" section to CLAUDE.md (model rotation, no preamble, prefer Grep over Agent, no unsolicited suggestions, no trailing summaries)
- [x] Tighten `.claude/settings.local.json` allowlist (skill found nothing universal to add; replaced wildcard `py *` with four explicit script invocations)
- [x] Default model: Sonnet 4.6. Downshift to Haiku for renames/format/lookup. Opus only for cross-file design or critique. (Documented in CLAUDE.md)
- [x] Keep CLAUDE.md under ~100 lines (every turn reads it) — currently ~60 lines

## B. Code hardening

- [x] Extract `scripts/dexcom_loader.py` — unifies the 4x duplicate `load_dexcom()`; ml_model's redundant dt-only bolus dedup dropped (set-based dedup is sufficient)
- [x] Extract `scripts/rules.py` — single source of truth for `thomas_rules()`; ASCII-only, parameterized thresholds preserved for ML
- [x] Add `tests/test_rules.py` — 18 unittest cases (fasting tiers + boundaries, hypo priority, activity stacking, clamp bounds, None inputs, threshold parameterization). Run: `py -X utf8 tests/test_rules.py`. Note: stdlib unittest, not pytest, because pytest isn't installed.
- [x] Persistent dose diary `data/doses.csv` — `scripts/dose_diary.py` module reads/upserts one row per dose-night; `dexcom_fetch` now anchors yesterday's dose from the diary instead of prompting, backfills yesterday's overnight outcome, pulls today's WHOOP strain from cache, and writes today's row with suggestion + reasoning. Prompt remains as fallback (EOFError-guarded) for first-ever run when no anchor is on file.
- [x] Portable paths — derive `DATA_DIR`/`API_DIR`/`PROJECT_ROOT` from `Path(__file__)` in 5 active path users (dexcom_loader, whoop_loader, dexcom_fetch, whoop_api_fetch, bolus_noise_test); deleted 4 dead `BASE`/`DIAGNOSIS` orphan declarations left over from the extraction refactors
- [x] Replace silent `except: pass` in CSV parsing with a skipped-row counter + load-time log. First run surfaces 677 skipped rows (~0.6%), likely Dexcom "Low"/"High" sentinels; root-cause investigation deferred.
- [x] Wrap `dexcom_fetch.py` `input()` in `try/except EOFError` so non-interactive runs don't crash
- [ ] Rename shadowed `TGT_LO`/`TGT_HI` — value 5/8 in `basal_analysis.py` (user goal) vs 4/10 in `rules_model.py`+`dexcom_fetch.py` (clinical TIR). Different intent, same name.
- [ ] Bolus dedup uses exact `(datetime, units)` tuple — 1-second timestamp drift across exports double-counts. Round to minute or dedup by (date, hour, units).
- [ ] Widen `whoop_api_fetch.py` retry net beyond 429 (handle 401 token-expired, 5xx server errors); per-endpoint isolation so one failure doesn't kill the other three
- [x] Fix cosmetic bug in `rules_model.py:164-165` — replaced literal `'="*70 + note...'` and `'="'*35` strings with proper note + divider
- [x] Removed `docs/analyze.py`, `docs/recalibrate.py`, `docs/REFERENCE.md` (superseded files); dropped "Do not use" pointer from CLAUDE.md

## C. Privacy / publishing

- [ ] CLAUDE.md contains full name, diagnosis date, email — sanitize before any public push, or keep repo private

## D. Known gaps (not bugs)

- Bolus log gap from 2026-01-31 (NovoPen 6 export pending)
- WHOOP `score.strain` only updates on app sync — `today_s1` often `None` at dose time
- Dexcom historical backfill via Clarity CSV is manual (Share API limited to 24h)

## Status

Section A complete (2026-05-15). B in progress: rules.py extraction and EOFError fix done; remaining items in priority order.
