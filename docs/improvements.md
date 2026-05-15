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
- [x] Persistent dose diary `data/doses.csv` — `scripts/dose_diary.py` module reads/upserts one row per dose-night; `dexcom_fetch` backfills yesterday's overnight outcome, pulls today's WHOOP strain from cache, and writes today's row with suggestion + reasoning.
- [x] Anchor priority fixed (post-B4): **Clarity CSV is authoritative**. dexcom_fetch tries Clarity first, falls through to diary, then prompts (EOFError-guarded) only as last resort. Clarity-derived dose backfills the diary's dose_u when present.
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

Sections A and most of B complete (2026-05-15). Remaining B items (B8/B9/B10) deferred -- low value-for-effort given current single-user manual-nightly workflow.

## E. Next session priorities

1. **GitHub integration**
   - Decision: public or private repo
   - If public: do C13 (sanitize CLAUDE.md -- name, diagnosis date, email) BEFORE first push
   - If private: just push as-is
   - Steps: `gh` CLI not installed -> create repo via web UI, then `git remote add origin <url>` + `git push -u origin master`

2. **Automation roadmap toward phone-driven nightly suggestion**
   - End goal: trigger from phone (Telegram bot), proactive 21:30 nightly push with tonight's suggestion
   - Stack: Python + python-telegram-bot, hosted on Hetzner Frankfurt (EU/GDPR) or Raspberry Pi at home
   - Phased plan (~6-9h total):
     - Phase 1 (~1h): `--dose N` CLI flag on dexcom_fetch; remove remaining input() prompts; make scripts cron-friendly
     - Phase 2 (~3-4h): Telegram bot with `/today`, `/took N`, `/stats` commands
     - Phase 3 (~30m): cron 21:30 -> bot DMs the suggestion proactively
     - Phase 4 (~2-4h, optional): Playwright nightly Clarity CSV export (gnarly; cached storage_state, monthly MFA refresh)
     - Phase 5 (optional): web dashboard for history graphs
   - Hard blocker for true end-to-end: Dexcom Share API has no insulin events; Clarity export is manual. Phase 4 solves it via browser automation OR user accepts periodic manual re-export.
   - Risks: MFA on Clarity, Dexcom ToS on automated access, UI brittleness, server uptime, Telegram chat-id whitelist for security
