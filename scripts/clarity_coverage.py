"""Clarity export coverage + gap detection.

Pure analysis over the glucose readings already loaded from Clarity CSVs:
reports per-day CGM coverage, finds the date ranges that still need
(re-)exporting, and reads/writes the confirmed-empty-day ledger. No browser
here - the Playwright exporter (`clarity_export.py`) consumes `find_gaps()`.

Coverage signal is glucose density (288 readings/day at 5-min cadence).
Insulin events are too sparse to detect gaps; a glucose-complete day implies
its insulin events were exported too.

Run a standalone report:
    py -X utf8 scripts/clarity_coverage.py
"""
import json
from datetime import date, timedelta
from collections import Counter

from dexcom_loader import load_dexcom, DATA_DIR

EXPECTED_PER_DAY      = 288          # one CGM reading per 5 minutes
MIN_READINGS_COMPLETE = 274          # 95% of EXPECTED_PER_DAY; below this = a gap
LEDGER_PATH           = DATA_DIR / 'clarity_known_empty.json'


def day_coverage(glucose_list=None):
    """Return {date: reading_count} from Clarity glucose readings.

    Loads from Clarity CSVs when glucose_list is not supplied; accepts an
    injected [(datetime, value), ...] list for testing.
    """
    if glucose_list is None:
        glucose_list, _, _ = load_dexcom()
    return dict(Counter(dt.date() for dt, _ in glucose_list))


def find_gaps(coverage, today, known_empty=frozenset()):
    """Contiguous date ranges that need (re-)exporting.

    A date in [first_reading .. today-1] is a gap when its coverage is below
    MIN_READINGS_COMPLETE and it is not in known_empty. Today is excluded
    (in-progress -> never a full day); the lower bound is the first observed
    reading, not the diagnosis date.

    Returns (ranges, gap_days):
      ranges   : sorted inclusive (start, end) date tuples
      gap_days : flat sorted list of every gap date
    """
    if not coverage:
        return [], []
    lower = min(coverage)
    upper = today - timedelta(days=1)

    gap_days = []
    d = lower
    while d <= upper:
        if d not in known_empty and coverage.get(d, 0) < MIN_READINGS_COMPLETE:
            gap_days.append(d)
        d += timedelta(days=1)

    ranges = []
    for d in gap_days:
        if ranges and d == ranges[-1][1] + timedelta(days=1):
            ranges[-1][1] = d
        else:
            ranges.append([d, d])
    return [(a, b) for a, b in ranges], gap_days


def load_ledger():
    """Return the frozenset of confirmed-empty dates from the ledger file."""
    if not LEDGER_PATH.exists():
        return frozenset()
    data = json.loads(LEDGER_PATH.read_text(encoding='utf-8'))
    return frozenset(date.fromisoformat(s) for s in data.get('confirmed_empty_days', []))


def save_ledger(days):
    """Write the confirmed-empty date set to the ledger file."""
    payload = {
        'confirmed_empty_days': sorted(d.isoformat() for d in days),
        'updated': date.today().isoformat(),
    }
    LEDGER_PATH.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _report():
    coverage = day_coverage()
    if not coverage:
        print('No Clarity glucose data found under data/.')
        return
    known = load_ledger()
    ranges, gap_days = find_gaps(coverage, date.today(), known)
    first, last = min(coverage), max(coverage)
    complete = sum(1 for c in coverage.values() if c >= MIN_READINGS_COMPLETE)
    print(f'Coverage: {first} -> {last} ({len(coverage)} days with data)')
    print(f'Complete days (>= {MIN_READINGS_COMPLETE}/{EXPECTED_PER_DAY}): {complete}')
    print(f'Ledgered (known-empty, skipped): {len(known)}')
    if ranges:
        print(f'Gap ranges to export ({len(gap_days)} days):')
        for a, b in ranges:
            n = (b - a).days + 1
            print(f'  {a} -> {b}  ({n} day{"s" if n > 1 else ""})')
    else:
        print('No gaps - data is complete through yesterday.')


if __name__ == '__main__':
    _report()
