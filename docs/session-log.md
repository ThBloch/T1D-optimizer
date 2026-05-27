# Session Log

Append one entry per session. Format:

```
## YYYY-MM-DD [workstream name if /renamed]
**Changed:** scripts or data modified
**Decided:** key decisions and reasoning (add to decisions-log.md if thomas_rules changed)
**Blocked:** current blockers
**Next:** planned next actions
```

---

## 2026-05-21
**Changed:** `.gitattributes` added; `docs/decisions-log.md` updated with GitHub strategy + C1 leak surface entries; `docs/improvements.md` restructured (E2 paths, E10 nighttime objective spec added, E3 blocked status updated).
**Decided:** Private GitHub backup pushed (https://github.com/ThBloch/T1D-optimizer). Public migration deferred until E1+E10+E5 done + C1 sanitized. `.gitattributes * text=auto` + `core.autocrlf=false` to lock line endings.
**Blocked:** Nothing blocking current work.
**Next:** E1 (strain rule refinement), E4 (`/t1d-status` command), or E5 (cron-friendly scripts).

## 2026-05-23
**Changed:** `CLAUDE.md` - added Decisions log protocol section and Compaction section. `docs/decisions-log.md` - added header/preamble, retrofit `Status: accepted` on all pre-convention entries.
**Decided:** Formal conventions adopted for decisions-log format (see `claude-setup/docs/decisions-log-conventions.md`). No content changes to existing entries, only structural additions.
**Blocked:** Nothing.
**Next:** Commit pending changes; then E1, E4, or E5.

## 2026-05-25
**Changed:** Nothing yet this session.
**Decided:** Nothing yet.
**Blocked:** Nothing.
**Next:** Commit CLAUDE.md + decisions-log.md formatting changes. Then pick next task from E1/E4/E5.

## 2026-05-26
**Changed:** `.claude/commands/t1d-status.md` created (new). `CLAUDE.md` Quick start updated with `/t1d-status` entry. `docs/improvements.md` E4 marked done. `hookify.decisions-log-reminder.local.md` - fix blocked by classifier (user to apply manually: change event to `file`, field to `file_path`). `scripts/dexcom_fetch.py` - replaced `sys.argv` with argparse, added `--dose N` flag at Priority 3. `.claude/commands/dose.md` created (new). `docs/improvements.md` E3 and E5 marked done.
**Decided:** E5: argparse replaces sys.argv; `--dose N` bypasses input() prompt, falls through to interactive if not given. E3: `/dose` command collects dose/new-pen/factors, runs script, handles hypo sensor-noise re-run, outputs terse suggestion. Both tested live.
**Blocked:** hookify rule fix still needs manual edit.
**Next:** E6 (Telegram bot, now unblocked) or E1 (strain rule refinement).
- Also added E5b to backlog: `/session-done` command to log session, commit, and push in one step.

## 2026-05-27 e1-strain-rule-analysis
**Changed:** `scripts/strain_binning_analysis.py` created (Phase A descriptive analysis, second-half slope per strain bin). `scripts/strain_regression_analysis.py` created (Phase A2 OLS regression of slope on dose + strain + interaction + controls). `output/strain_binning.txt` and `output/strain_regression.txt` generated (not committed - output/ gitignored). Plan file at `C:\Users\thblo\.claude\plans\explail-e1-bubbly-cerf.md`. New memory `feedback-night-quality-slope` saved.
**Decided:**
- Night-quality outcome metric is **second-half glucose slope** (down = dose too high, up = too low, flat = correct), not TIR alone. Per Thomas, "this way of analysing data is also important to do." See new memory `feedback-night-quality-slope`.
- Phase A descriptive binning insufficient on its own - tells us slope at the dose actually taken, not the optimal dose for each strain level. Phase A2 regression added to fix this.
- Phase A2 results: 256 usable nights, `b_strain` = -0.054 mmol/L/h per strain unit, **p=0.001 (robust)**. `b_dose` weak (p=0.43 additive, p=0.02 with interaction) because Thomas's historical dose range is narrow (15-29, mostly 17-19) - can't measure dose-slope coefficient reliably from data alone.
- Interaction model produces a singularity (b_dose + b_interact*s1 → 0 near s1=11.5), physiologically nonsense. Dropped in favor of additive model.
- Direction confirmed by both data and Thomas's observation: low dose → glucose jumps up (under-dose); high dose → glucose drops down (over-dose). Low strain → insulin resistance (+adj); high strain → insulin sensitivity (-adj).
- Used Thomas's bolus ISF (~1.5-2.0 mmol/L per unit) to estimate Lantus basal slope coefficient at ~0.09 mmol/L/h per unit - working number, can revise. Thomas pushed back that thresholds must be data-driven; treat the clinical prior as a fallback only where data underdetermines.
- E1b (WHOOP in-progress cycle indexing fix) initially treated as out of scope; **later elevated** - see continuation below.
**Blocked:** Phase B encoding gated on Thomas signing off on the 6-tier threshold table. Current proposed table (data-anchored to observed per-bin slopes from binning report):
| Adj | s1 range | Evidence |
|-----|----------|----------|
| +3 | s1 < 6 | rest fixed-bin (n=12), slope +0.19 - thin evidence, physiology-warranted |
| +2 | 6 ≤ s1 < 9 | strongest under-dose, slope +0.30 to +0.33 |
| +1 | 9 ≤ s1 < 11 | transition out of under-dose zone, slope +0.05 to +0.20 |
| 0  | 11 ≤ s1 < 13 | flat (-0.03 to +0.05), confirms current "no adj at moderate" |
| -1 | 13 ≤ s1 < 15 | currently -2, flat - granularity move (will shift mildly upward) |
| -2 | s1 ≥ 15 | peak, current cap holds (slope -0.21 to -0.35) |
Thomas may shift any threshold before encoding.

### 2026-05-27 (continued, post-pause)
**Changed:** `docs/improvements.md` - E1 updated with status pointer to this session; E1b promoted from "deferred" to active with three strategy options; new item **E1c** added (line-by-line rule audit + per-rule skip toggle). New memory `feedback-rule-parameter-ownership` saved (+ MEMORY.md index updated). `data/doses.csv` got two rows from `/dose 24` run (2026-05-26 backfill + 2026-05-27 suggestion 24u "Fasting 10.3 in range -> no adjustment").
**Decided:**
- **Strain non-negotiable**: every dose suggestion MUST include a strain reasoning line. Silent skip when WHOOP in-progress cycle returns `None` is unacceptable. This re-elevates E1b ahead of Phase B encoding.
- **Rule ownership**: Thomas does NOT recognise the current `thomas_rules` thresholds (FASTING_LO=10.5, FASTING_MID=12.0, FASTING_HI=14.0, ACTIVITY_THR=12.0, DOSE_MIN=15, DOSE_MAX=29) as values he personally set. They were inherited/defaulted. Triggered by tonight's 10.3 fasting not firing +1u because 10.3 < 10.5. New backlog item E1c will surface every rule to Thomas with current value + source + historical firing count, then add per-rule skip toggle.
**Blocked:** Phase B (E1 encoding) still gated on threshold sign-off. Now also recommend running **E1b** before or in parallel with Phase B so the new strain rule actually fires every night.
**Next:**
1. Pick up E1b - implement one of: live whoop-sdk fetch at dose-suggestion time, fallback to yesterday's cycle s1 with flag, or interactive prompt fallback. Acceptance: `dexcom_fetch.py` always emits a strain reasoning line.
2. Start E1c rule audit - enumerate every threshold + branch in `scripts/rules.py`, surface to Thomas, accept/modify/skip, then implement the skip-toggle (CLI flag or `ENABLED_RULES` config) and a new `docs/rules-spec.md`.
3. Phase B (E1 encode) once E1b lands and Thomas signs off on thresholds.
