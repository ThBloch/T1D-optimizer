---
description: Get tonight's basal dose suggestion from live Dexcom data
---

# /dose

Run dexcom_fetch.py, then react to what it reports. Every prompt below is
conditional on the run's output - do not gather inputs up front.

## Steps

Maintain a FLAGS string, initially empty. Append to it as conditions are
discovered, and re-run the command (replacing OUTPUT) after each change.

1. Ask: "New pen cartridge tonight? (y/n)"
   If y, append `--new-pen` to FLAGS.

2. Run:
   ```bash
   cd "D:/claude/t1d/scripts" && py -X utf8 dexcom_fetch.py FLAGS
   ```
   Capture full stdout as OUTPUT. (FLAGS expands to the flags collected so
   far; empty on the first run.)

3. Anchor dose. If OUTPUT contains `no anchor dose on file`:
   - Ask: "What dose did you take last night? (units)" -> DOSE
   - Append `--dose DOSE` to FLAGS, re-run step 2, replace OUTPUT.

4. Strain. If OUTPUT contains `NEEDS: strain`:
   - Ask: "Today's WHOOP strain isn't synced yet. What's today's strain?" -> STRAIN
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
