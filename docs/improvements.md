# Improvement Backlog

Generated 2026-05-15 from architecture critique. Read this before proposing new refactors.

## A. Token saving (priority)

- [x] Add "Working preferences" section to CLAUDE.md (model rotation, no preamble, prefer Grep over Agent, no unsolicited suggestions, no trailing summaries)
- [x] Tighten `.claude/settings.local.json` allowlist (skill found nothing universal to add; replaced wildcard `py *` with four explicit script invocations)
- [x] Default model: Sonnet 4.6. Downshift to Haiku for renames/format/lookup. Opus only for cross-file design or critique. (Documented in CLAUDE.md)
- [x] Keep CLAUDE.md under ~100 lines (every turn reads it) — currently ~60 lines

## B. Code hardening

- [ ] Extract `scripts/dexcom_loader.py` — `load_dexcom()` is duplicated 4x (basal_analysis, rules_model, ml_model, predictor_test)
- [x] Extract `scripts/rules.py` — single source of truth for `thomas_rules()`; ASCII-only, parameterized thresholds preserved for ML
- [ ] Add `tests/test_rules.py` — ~10 pytest cases covering hypo paths, fasting tiers, activity stacking, clamp boundaries
- [ ] Persistent dose diary `data/doses.csv` — append-only after each `dexcom_fetch` run; eliminates the interactive `input()` prompt that broke our headless run
- [ ] Portable paths — replace `BASE = 'D:/claude/t1d/data'` with `Path(__file__).resolve().parent.parent / 'data'`
- [ ] Replace silent `except: pass` in CSV parsing with a skipped-row counter + load-time log
- [x] Wrap `dexcom_fetch.py` `input()` in `try/except EOFError` so non-interactive runs don't crash
- [ ] Rename shadowed `TGT_LO`/`TGT_HI` — value 5/8 in `basal_analysis.py` (user goal) vs 4/10 in `rules_model.py`+`dexcom_fetch.py` (clinical TIR). Different intent, same name.
- [ ] Bolus dedup uses exact `(datetime, units)` tuple — 1-second timestamp drift across exports double-counts. Round to minute or dedup by (date, hour, units).
- [ ] Widen `whoop_api_fetch.py` retry net beyond 429 (handle 401 token-expired, 5xx server errors); per-endpoint isolation so one failure doesn't kill the other three
- [ ] Fix cosmetic bug in `rules_model.py:242` — `print(f'="*70 + note...')` is a literal f-string, not what was intended
- [ ] Decide fate of `docs/analyze.py`, `docs/recalibrate.py`, `docs/REFERENCE.md` (marked "do not use" but tracked) — delete or move to `archive/`

## C. Privacy / publishing

- [ ] CLAUDE.md contains full name, diagnosis date, email — sanitize before any public push, or keep repo private

## D. Known gaps (not bugs)

- Bolus log gap from 2026-01-31 (NovoPen 6 export pending)
- WHOOP `score.strain` only updates on app sync — `today_s1` often `None` at dose time
- Dexcom historical backfill via Clarity CSV is manual (Share API limited to 24h)

## Status

Section A complete (2026-05-15). B in progress: rules.py extraction and EOFError fix done; remaining items in priority order.
