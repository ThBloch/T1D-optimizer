---
description: Get tonight's basal dose suggestion from live Dexcom data
---

# /dose

Run dexcom_fetch.py, then react to what it reports. Every prompt below is
conditional on the run's output - do not gather inputs up front.

## Steps

Maintain a FLAGS string, initially empty. Append to it as conditions are
discovered, and re-run the command (replacing OUTPUT) after each change.

0. Refresh API caches:
   ```bash
   py -X utf8 "D:/claude/t1d/scripts/dexcom_events_fetch.py"
   ```
   (Incremental; typically <10s. Run before dexcom_fetch.py so the overnight
   glucose window and basal anchor are fresh.)

1. Ask: "New pen cartridge tonight? (y/n)"
   If y, append `--new-pen` to FLAGS.

2. Run:
   ```bash
   cd "D:/claude/t1d/scripts" && py -X utf8 dexcom_fetch.py FLAGS
   ```
   Capture full stdout as OUTPUT. (FLAGS expands to the flags collected so
   far; empty on the first run.)

3. Anchor dose. If OUTPUT contains `NEEDS: dose`:
   - Ask: "What dose did you take last night? (units)" -> DOSE
   - Validate: must be a positive number. Re-ask if blank or non-numeric.
   - Append `--dose DOSE` to FLAGS, re-run step 2, replace OUTPUT.

4. Strain. If OUTPUT contains `NEEDS: strain`:
   - Ask: "WHOOP strain for today (check app):" -> STRAIN
   - Validate: must be a number (e.g. 12.4). Re-ask if blank or non-numeric.
   - If STRAIN < 0 or STRAIN > 21: warn "Outside normal WHOOP range (0-21), proceeding anyway" then continue.
   - Append `--strain STRAIN` to FLAGS, re-run step 2, replace OUTPUT.

5. Hypo. If OUTPUT has a line matching `Hypo events.*: [1-9]`:
   - Ask: "CGM detected N hypo(s) last night. Sensor noise? (y/n)"
   - If y: append `--no-hypo` to FLAGS, re-run step 2, replace OUTPUT.

6. Guard. If OUTPUT has no `Suggested dose` line: print the `Not enough readings`
   line from OUTPUT verbatim and stop. Skip the remaining steps. (Sensor-gap
   night - the overnight window held fewer than 4 CGM points.)

7. Ask: "Any unmodeled factors? (alcohol / late meal / illness / activity not in WHOOP - or 'none')"
   Store as FACTORS.

8. Extract from OUTPUT:
   - Suggested dose: find line matching `Suggested dose\s*:\s*(\S+)` -> SUGGESTION
   - Reasoning: collect all lines starting with `    * ` -> REASONS

9. Print:
   ```
   Tonight: SUGGESTION
   * reason 1
   * reason 2
   ...
   ```
   If FACTORS is non-empty and not "none":
   ```
   Off-rules: FACTORS (not modeled)
   ```

Print nothing else. No prose, no headers, no commentary beyond the lines above.
