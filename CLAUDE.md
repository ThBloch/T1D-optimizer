# T1D Basal Optimizer

Thomas Bloch-Nielsen — T1D diagnosed 2025-04-09.

## Quick start
```
cd D:/claude/t1d/scripts
py -X utf8 basal_analysis.py     # main analysis + tonight's suggestion
py -X utf8 rules_model.py        # rules backtest + tonight's rule-based suggestion
py -X utf8 dexcom_fetch.py       # live CGM via Dexcom Share API
py -X utf8 whoop_api_fetch.py    # refresh WHOOP JSON cache from API
```

## Structure
```
data/                     Dexcom Clarity CSVs (semicolon, Danish locale)
data/whoop_api/           WHOOP raw API responses (cycles/recovery/sleep/workouts.json)
scripts/                  all active analysis code
archive/whoop_csv/        old my_whoop_data_* directories (superseded by API)
archive/scripts_pre_api/  pre-JSON-loader script versions
docs/                     architecture, decisions, progress, superseded files
output/                   generated reports (not committed)
```

## Scripts
- `basal_analysis.py` — main analysis (matching model, weekly pattern, tonight's range)
- `rules_model.py` — Thomas's rules backtest + tonight's suggestion
- `predictor_test.py`, `ml_model.py`, `bolus_noise_test.py` — secondary analyses
- `whoop_loader.py` — shared loader, reads `data/whoop_api/*.json` → `{date: {strain, recovery, hrv, rhr, sleep_perf}}`
- `dexcom_fetch.py` — daily CGM fetch via `pydexcom` (Share API, region OUS, 24h window)
- `whoop_api_fetch.py` — incremental WHOOP refresh via `whoop-sdk` (4 endpoints, 7-day overlap cursor, dedup-merge by id/cycle_id, 429 backoff). `--full` flag forces backfill from 2025-04-09. Typical run ~4s.

## Data sources (API-driven)
- **Dexcom**: `pydexcom` Share API. Creds at `D:/claude/t1d/dexcom_creds.json` (plaintext). Returns tz-aware local datetimes; `dexcom_fetch.py` strips tzinfo for downstream comparisons. Share API limited to last 24h — for historical backfill use Clarity CSV exports.
- **WHOOP**: official Developer API via `whoop-sdk`. OAuth tokens at `~/.whoop_sdk/config.json`, app credentials at `~/.whoop_sdk/settings.json`. WHOOP CSV exports superseded by JSON cache.

## Key facts
- Run with `py` not `python3` (Windows)
- Dexcom CSV: semicolon-delimited, Danish locale, mmol/L, comma decimals
- Target: fasting 5–8 mmol/L | hypo <4.0 | hyper >10.0
- Bolus logging gap: from 2026-01-31 (switched to NovoPen 6 — data not yet exported)
- WHOOP in-progress cycle dating: indexed under start date, so `today_s1` lookup often returns None at dose time — fetch live via API when needed
- WHOOP strain freshness: `score.strain` only updates on WHOOP app sync — check `updated_at`

## Working preferences (token-saving)
- Default model: Sonnet 4.6. Haiku for renames/format/lookup. Opus only for cross-file design or critique.
- No preamble, no trailing summaries, no unsolicited suggestions.
- Reference file paths instead of pasting file contents.
- Prefer Grep/Read/Glob over spawning Agents. Spawn only for genuinely open-ended multi-step research.
- Backlog at `docs/improvements.md` - read before proposing new refactors.

## Full model context
See memory file or `docs/architecture.md`.
