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

## 2026-05-28 e1b-design-spar
**Changed:** Nothing applied this session. Discussion + capture only - Thomas wants to work on the actual changes later. This entry exists so the next session can resume seamlessly.

**Discussed:** E1b design - "always provide a usable s1 at dose time" - and discovered the same class of bug applies to the dose-anchor question in `/dose`. Plan-mode session; deep design sparring driven by Thomas's pushback on Claude's initial framing.

**Original framing (before Thomas's corrections):**
- Problem (unchanged from yesterday): `scripts/whoop_loader.py:18-23` indexes the in-progress WHOOP cycle under its start date, so `whoop.get(today)` returns `None` at evening dose-suggestion time. `dexcom_fetch.py:177-182` then silently calls `thomas_rules(s1=None)`, skipping the strain branch. No strain reasoning line is emitted; no activity adjustment is applied. Thomas considers this unacceptable (see `feedback_rule_parameter_ownership` and the 2026-05-27 entry above: strain MUST inform every suggestion).
- Initial /dose-command-only proposal (Claude): add a "Today's WHOOP strain? (enter to use cached value)" question to /dose step 1; pass as `--strain N` flag. Thomas pushed back: `/dose` should only ask for things that are not already available in the data.
- Refined cross-cutting proposal: the same bug class affects the dose-anchor question. `/dose` step 1 always asks for yesterday's dose, but `dexcom_fetch.py` already auto-resolves yesterday's dose from Clarity CSV first, then the diary - so the question is usually redundant. Fix both in one pass: script signals what it could not auto-resolve on stdout via structured lines (`NEEDS: dose`, `NEEDS: strain`); slash command parses stdout, asks only for the missing items, then re-runs the script with the missing values passed as flags.
- Layered strain-resolution Claude initially proposed: WHOOP cache (today) -> WHOOP live-fetch (in-progress cycle via `whoop-sdk`) -> yesterday's s1 as proxy with a flag in the reasoning line -> interactive manual prompt as last resort.
- Signaling-mechanism analysis: structured stdout lines preferred over exit codes because (a) a single integer cannot cleanly encode multiple missing items - would require bitmask encoding that breaks at the third input type, (b) `/dose` already parses stdout with regex (steps 5+6 do exactly this for hypo events and suggested dose), (c) `NEEDS:` lines are human-readable when running the script manually from a terminal, which matters for debugging. Exit codes rejected.

**Thomas's corrections (2026-05-28) - all four are load-bearing:**

1. *Automation goal had been misframed by Claude.* The Telegram bot (improvements.md section E, phases E6/E7) is for **remote** suggestion requests from Thomas's phone when he is away from his home computer. It is NOT a scheduled nightly push. Dose decisions are always active, user-initiated choices - Thomas decides when to inject and asks for a suggestion at that moment. The bot would never silently trigger or push a suggestion at a fixed time. Multi-turn interactive prompts in the bot are explicit and welcome - chat handles them naturally. Claude's earlier argument that "interactive prompts conflict with the automation goal" is wrong and must be discarded. Implication: layered design with interactive prompts is fine; the bot can replicate the same prompt flow as the local `/dose` command.

2. *Yesterday's strain is never a usable proxy for today's strain.* Strategy 2 from the original E1b ("fall back to most recent closed cycle, flag it in the reasoning line") is dropped entirely. Strain varies day-to-day; yesterday's value is not representative of today's insulin sensitivity. Using it produces a wrong dose suggestion that is **worse** than omitting strain or asking the user. Exactly two valid resolution paths remain: (a) today's strain from WHOOP (cache lookup, plus possibly live-fetch the in-progress cycle), (b) ask Thomas directly.

3. *WHOOP live-fetch is an exploration item, not a decided design.* Whether `whoop-sdk` exposes the in-progress cycle and whether `score.strain` is populated mid-day before the cycle closes both need investigation. Add this as exploratory sub-work; do not commit to it as the chosen fallback. If exploration shows live-fetch is viable, it slots in between cache and manual prompt. If not, manual prompt is the only fallback.

4. *Manual fallback prompt steps must be documented.* When strain (or any input) cannot be auto-resolved and `/dose` must ask, the prompt flow needs a written spec: what is asked, in what order, with what wording, what input formats are accepted, validation rules, what happens if the user can't provide a value. This is a sub-todo of its own and gates the implementation of the NEEDS-line protocol. Thomas considers undocumented manual prompts unacceptable.

**Changes to apply later (NOT applied this session - this is the to-do):**

A. NEW memory file at `C:\Users\thblo\.claude\projects\D--claude-t1d\memory\feedback_strain_yesterday_invalid.md`:
   - Frontmatter: `name: feedback-strain-yesterday-invalid`, `type: feedback`, description "Never use yesterday's WHOOP strain as a substitute for today's strain".
   - Body (lead with rule, then Why, then How to apply):
     - Rule: Never use yesterday's WHOOP strain as a proxy for today's strain. Drop any fallback chain that includes "use yesterday's s1 if today's is unavailable".
     - Why: Strain varies day-to-day. Yesterday's value is not representative of today's insulin sensitivity. Using it produces a wrong dose suggestion that is worse than omitting strain or asking the user. Thomas confirmed explicitly 2026-05-28.
     - How to apply: In any code path that needs today's strain and the WHOOP cache returns None, do not look at yesterday's cycle. Two valid paths only: resolve today's strain (cache or live-fetch), or ask the user directly. Link to [[feedback-rule-parameter-ownership]] and [[feedback-night-quality-slope]] as related context.
   - Add to `MEMORY.md` index: `- [Strain yesterday invalid](feedback_strain_yesterday_invalid.md) - Never use yesterday's strain as a proxy for today's strain`

B. UPDATE memory file `project_automation_goal.md`:
   - The current entry (per MEMORY.md index) reads "Phone-driven nightly suggestion via Telegram bot; phased roadmap in improvements.md section E". This implies a scheduled push and is wrong.
   - Updated framing must say: The Telegram bot is for **remote suggestion requests** (Thomas asking for a suggestion when away from his home computer). Always user-initiated. Never a scheduled push. Dose decisions are active choices Thomas makes; the system supports them, never triggers them. Multi-turn interactive prompts in the bot are welcome - chat handles them naturally.
   - Action item: read the current file body and rewrite the relevant paragraph(s). Update the MEMORY.md index line too if the description still implies a scheduled flow.

C. UPDATE `docs/improvements.md` E1b entry - rewrite the design body. Current body is in two pieces: the original entry (lines ~38-43 before today's expansion) and the 2026-05-28 expansion Claude added earlier in this session (lines ~38-50 currently). Both need to be reconciled and corrected. New body should:
   - Keep the problem statement (WHOOP in-progress cycle indexing causes None at evening dose time; `dexcom_fetch.py` silently skips strain).
   - Remove the strategy enumeration "(pick one or stack)" and remove strategy 2 (yesterday's s1 as proxy) entirely. Per correction #2 above.
   - Replace the strategies list with the corrected design:
     - Two valid strain-resolution paths only: (a) today's WHOOP strain from cache (and possibly live-fetch - see exploration sub-task), (b) ask Thomas via documented prompts.
     - Sub-task to explore (does not block implementation): live-fetch the in-progress cycle from `whoop-sdk` at dose-suggestion time. Investigation goals: does the SDK return the in-progress cycle? Is `score.strain` populated mid-day before the cycle closes? If yes -> integrate as a path between cache lookup and manual prompt. If no -> manual prompt is the only fallback for cache-miss days. Mark this sub-task as exploration only; do not commit to it as the design.
     - Sub-task to document (gates implementation): the manual fallback prompt steps - see D below.
     - Generalization decided this session: the same `NEEDS:`-line protocol applies to the dose anchor too. `/dose` step 1 currently asks for yesterday's dose upfront, but `dexcom_fetch.py` already auto-resolves it from Clarity then diary. Defer asking until the script signals `NEEDS: dose`. Apply the same pattern to strain via `NEEDS: strain`.
   - Signaling mechanism (decided this session): structured stdout lines of the form `NEEDS: <name>` (e.g. `NEEDS: dose`, `NEEDS: strain`). The slash command parses these from script stdout, asks only for the listed missing items using documented prompt wording, then re-runs the script with the values passed as flags (`--dose N`, `--strain N`). Exit codes were considered and rejected: (a) cannot cleanly encode multiple missing items in a single integer without fragile bitmask encoding, (b) inconsistent with the existing `/dose` stdout-parsing approach (hypo re-run already does this in step 5), (c) less human-readable when running the script manually.
   - Acceptance criteria (refined): `dexcom_fetch.py` never silently skips strain. If strain cannot be resolved by the available auto-paths, the script emits `NEEDS: strain` on stdout. `/dose` parses stdout for `NEEDS:` lines, asks only for the missing items using the documented prompt wording, then re-runs the script with the missing values passed as flags. The script must never block on `input()` in non-interactive mode (already true for the dose anchor since B8; extend to strain).

D. NEW sub-todo entry (placement TBD - could be a sub-bullet under E1b, or a sibling item like E1d). Title: "Document the manual-fallback prompt steps for `/dose`."
   - Open questions to resolve before writing the spec:
     - Wording: e.g. "What was today's WHOOP strain (0-21)?" - or alternative framing? Should the prompt include a hint about typical values or expected range?
     - Validation: accept floats (typical strain readings are like 12.4)? Reject if outside 0-21? Reject negative numbers and non-numeric input?
     - "I don't know" path: is "skip" an acceptable answer for strain? If yes, what happens downstream - does the script run without strain (silent skip again, contradicting the non-negotiable rule)? Or does it use a documented default? Or does it refuse to suggest a dose at all? Thomas must decide.
     - Order of asks: if both dose AND strain are missing in the same run (rare - typically only on first run of a new install with no Clarity CSV and no diary), ask dose first or strain first? Suggestion: dose first, because the script cannot suggest a dose at all without it; strain is graceful-degrade-only if "skip" is allowed.
     - Re-run flow: after collecting missing inputs, `/dose` re-invokes `dexcom_fetch.py` with `--dose N --strain N` (or whichever subset was missing). Confirm the script supports both flags and that the rerun does not infinite-loop on persistent `NEEDS:` lines (e.g. if user types an invalid value, the script re-emits `NEEDS:` - but `/dose` should not loop forever; max two passes or per-item retry).
     - Output medium: do the prompts live as inline text in `.claude/commands/dose.md`, or as a separate referenced doc like `docs/dose-manual-prompts.md`? Inline is simpler; separate is more reusable when the Telegram bot replicates the same prompts.
   - Output of this sub-todo: a "Manual fallback prompts" section in `.claude/commands/dose.md` (or a referenced doc) with the exact prompt strings, validation rules, and order of operations.

**Code changes implied (NOT in scope for the documentation pass, but listed here so future-Claude scopes them next):**
- `scripts/dexcom_fetch.py`: replace the Priority-3 interactive `input()` dose prompt (currently lines ~162-174) with `print("NEEDS: dose")` + `return`. Replace the silent strain-None path (currently lines ~181-182) with `print("NEEDS: strain")` + continue-without-strain-but-still-no-suggestion (or `return`, depending on the "skip" decision in D). Add `--strain N` flag, mirror of `--dose N`. Wire the flag into the WHOOP lookup so the flag overrides the cache.
- `.claude/commands/dose.md`: remove the upfront dose question (step 1). New flow: run script with no flags -> parse stdout for `NEEDS:` lines -> ask only for those using the documented prompt wording -> re-run with appropriate flags. Existing hypo re-run pattern (step 5) is the model.
- Tests: `tests/test_rules.py` likely needs no new cases since rule logic does not change. But `dexcom_fetch.py` integration behavior could benefit from a smoke test that asserts `NEEDS:` lines are emitted on missing inputs. Out of scope for current test framework which is `thomas_rules`-focused.
- Live-fetch (exploration from C above) is independent and not on the critical path; can be done in parallel or deferred entirely.

**Blocked:** Nothing technical. Thomas explicitly does not want to apply these changes now - he wants to work on them later.

**Next (when Thomas resumes - exact order):**
1. Apply memory updates A (new `feedback-strain-yesterday-invalid` file + MEMORY.md index entry).
2. Apply memory update B (`project-automation-goal` rewrite, plus MEMORY.md index line if needed).
3. Rewrite E1b in `docs/improvements.md` per C.
4. Add sub-todo D for manual-fallback prompt documentation (decide placement: nested under E1b, or sibling like E1d).
5. Then scope and implement the actual code changes (the "Code changes implied" block above).
6. Live-fetch exploration is independent and can run in parallel or be deferred.

**Open questions Thomas may want to weigh in on before next session:**
- Sub-todo D, "I don't know" path: if Thomas can't answer the strain prompt, what does `/dose` do? Refuse to suggest? Run without strain? Use a documented default? This decision shapes the rest of the manual-fallback flow.
- Live-fetch viability: anyone planning to read `whoop-sdk` docs to answer "does it expose the in-progress cycle"? Could be done by Claude in a future session if Thomas wants it scoped.
- Bot replication: when E6 (Telegram bot) gets built, the manual prompts in `/dose` will need to be replicated in the bot. Designing the prompt spec as a separate doc (not inline in `dose.md`) makes that reuse easier - relevant to sub-todo D's "output medium" question.

## 2026-05-28 (continued) architecture-doc-walkthrough
**Changed:** `docs/architecture.md` - Thomas added inline annotations to section 1 ("matching model is incorrect" + new "math model" entry as #3). No other files modified this turn.

**Discussed:** architecture.md section-by-section. Six sections total; covered sections 1-4 this turn. Sections 5-6 still to walk.

**Decisions (sections 1-4):**

**Section 1 - "What we predict": ranking and labeling.**
- Target ranking: 1=Math model, 2=Rules model, 3=Matching model.
- Current ranking: Rules is primary; Math does not yet outperform (decision-tree MAE 1.45u vs rules 1.32u per current backtest).
- Doc should describe BOTH states with labels ("Current primary: Rules. Target primary: Math.").
- Draft table proposed (architecture.md section 1 rewrite candidate):

  | Rank | Model | Script | Approach |
  |---|---|---|---|
  | 1 | Math model | `ml_model.py` | sklearn pipeline; 80/20 time-based train/test split; predicts TIR% per candidate dose |
  | 2 | Rules model | `rules_model.py` | encodes `thomas_rules()`; backtests; suggests via anchor + adjustments |
  | 3 | Matching model | `basal_analysis.py` | observational - finds historical nights similar on (inj_g, s1) |

  Plus two labeled lines: "Current primary: Rules" / "Target primary: Math".
- Implication: `CLAUDE.md` Quick start labels `basal_analysis.py` as "main analysis + tonight's suggestion". That contradicts "rules-primary" framing. Needs updating when section 1 is rewritten.

**Section 3 - Exclusion rules: both amended.**
- **Rule 1 (hypo-correction nights):** threshold 7.0 -> 10.0.
  - Today: post-hypo recovery above 7.0 flags the night as hypo-correction (excluded from matching, shown as DOSE>HIGH).
  - New: only flag when post-hypo max exceeds 10.0. Fewer nights flagged; more nights retained for matching.
  - Code touchpoints: `basal_analysis.py:48` (`if max(post) > 7.0`), `basal_analysis.py:50-51, 74` (redundant `correction_spike_above_10` flag collapses into main `hypo_correction`), `ml_model.py:45` (`max(vals[hypo_idx:])>7.0`).
  - Architecture.md cite "58/297 nights (19.5%)" will be stale after the recomputation.
- **Rule 2 (high-bolus outlier nights):** removed entirely.
  - Reason: bolus data unreliable since 2026-01-31 NovoPen switch. Bolus is not a stable exclusion criterion until digital-pen data has accumulated.
  - Re-evaluate later when post-NovoPen bolus data is plentiful.
  - Code touchpoints: `basal_analysis.py:123-133` (`iqr_bolus_outlier()` function), `basal_analysis.py:195-205` (exclusion logic in main flow), `[bolus]` annotations in weekly summary loop.
  - Architecture.md "(bolus confounder, r=-0.29 p<0.001)" cite goes away when section 3 is rewritten.

**Section 4 - Titration rules: fasting tier overhauled.**
- **Clamp 15-29u:** confirmed correct. Future-work note: may be adjusted based on general fitness / stress level. Logged as future investigation, NOT in current scope.
- **Fasting +1u threshold:** 10.5 -> 10.0 (incremental fix; resolves 2026-05-27 complaint about fasting 10.3 not firing the +1u rule).
- **Structural shift: fasting tier rule replaced by slope-based rule.**
  - Decision: dose adjustment reacts to overnight CGM slope direction/magnitude, not endpoint fasting at 07:00.
  - "Level" adjustments belong to bolus (correction doses), not basal. Slope is basal's signal.
  - Slope window: **second half of night** (matches Phase A2 outcome metric; fraction-based last 50% of overnight CGM readings).
  - Slope **alone** drives the rule trigger - no combined slope+level check. Level corrections are bolus's job.
  - Magnitude **scales with slope steepness** (Option A from the three offered).
  - **HARD BLOCKER:** bolus data needed to disambiguate "basal too low" from "I corrected mid-night with a bolus". Without bolus history, slope-based rule cannot be safely deployed. NovoPen 6 bolus integration is now a prerequisite, not a "nice to have".
- **Other section-4 rules not yet addressed this session (still stand as-is):**
  - Fasting +2u threshold (FASTING_MID=12.0) - will be subsumed if entire fasting tier becomes slope-based
  - Fasting +3u threshold (FASTING_HI=14.0) - same
  - Activity rule (s1 >= 12 -> -2u) - being replaced by E1's 6-tier scale anyway
  - New pen -1u - not discussed
  - Hypo events: -1u for 1, -2u for >=2 - not discussed

**Open questions still pending on the slope-based rule:**
- Down-direction symmetry: falling slope without a hypo - triggers -u, or stay neutral and let hypos drive down? (Thomas's 2026-05-27 comment "high dose -> glucose drops down" argues for -u; current rule waits for actual hypo before going down.)
- Slope thresholds: define educated-guess values now (e.g. 0.2 / 0.5 / 1.0 mmol/L per hour) or wait until bolus-cleaned backtest can validate?
- Adjustment scale: keep 3-tier (+1/+2/+3) or finer/coarser?
- Hypo priority structure: still required, or does the slope encode hypo severity already (since a hypo is part of the trajectory)?

**Changes to apply later (NOT applied this session - all captured for resume):**

**A. `docs/architecture.md` rewrite.**
- Section 1: replace flat numbered list with current+target table (see draft above). Reorder math/rules/matching as target ranking; add Current vs Target labels.
- Section 3: Rule 1 threshold 7 -> 10; Rule 2 removed; "58/297 nights (19.5%)" stat needs recomputing.
- Section 4: fasting +1u threshold update; full section rewrite once slope-based rule is finalised.
- Strip em-dashes throughout (ASCII-only convention from global CLAUDE.md). Multiple instances.

**B. `scripts/rules.py` updates.**
- `FASTING_LO = 10.5` -> `10.0`.
- Eventually: replace fasting-tier branch entirely with slope-based logic (gated on bolus integration).
- Tests on the 10.5 boundary in `tests/test_rules.py` need updating.

**C. `scripts/basal_analysis.py` updates.**
- Line 48: hypo-correction threshold 7.0 -> 10.0.
- Collapse redundant `correction_spike_above_10` flag into `hypo_correction`.
- Remove `iqr_bolus_outlier()` (lines 123-133) and bolus-exclusion logic in main flow (lines 195-205).
- Remove `[bolus]` annotations in weekly summary loop.

**D. `scripts/ml_model.py` updates.**
- Line 45: hypo-correction threshold 7.0 -> 10.0.

**E. `docs/improvements.md` backlog additions.**
- New item: slope-based fasting rule definition + implementation. Gated on F (bolus integration). Inherits the open questions above.
- New item: NovoPen 6 bolus integration. Elevate from "known gap" in Background section to an active prerequisite for the slope-based rule.

**F. `docs/decisions-log.md` entries (when each change ships).**
- Hypo-correction threshold 7 -> 10 (with new "% nights flagged" stat).
- Bolus IQR exclusion removal (with reason: post-NovoPen data unstable).
- Fasting +1u threshold 10.5 -> 10.0.
- Fasting tier -> slope-based shift (large decision; will likely need its own entry with the resolved open questions).

**G. `CLAUDE.md` Quick start update.**
- `basal_analysis.py` labelled "main analysis + tonight's suggestion" is misaligned with the rules-primary framing. Reword or downgrade.

**Blocked:** Slope-based rule (section 4 main change) depends on NovoPen 6 bolus integration (item E).

**Next (when Thomas resumes architecture walkthrough):**
1. Resolve the 4 open questions on the slope-based rule (down-direction, thresholds, scale, hypo priority).
2. Walk section 5 (Why ML underperforms) and section 6 (Data pipeline).
3. Then apply A-G in dependency order. Likely apply non-blocked items first (architecture.md rewrite, rules.py FASTING_LO change, basal_analysis.py + ml_model.py threshold change, bolus exclusion removal). Slope-based rule waits for bolus integration.
