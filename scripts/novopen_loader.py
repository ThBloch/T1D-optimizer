"""Glooko export loader for NovoPen 6 bolus events.

Reads `data/glooko/Insulin data/insulin_data_1.csv` and applies
Glooko's documented Prime Detection rule via
`scripts/bolus_classification.filter_primes`.

Only events from the smart pen are kept; Dexcom-source rows
(Thomas's manual basal entries) are skipped - basal lives in
Clarity.

I/O + parsing only (P5). Classification logic lives in
`bolus_classification`; this module just calls into it.
"""
import csv
from datetime import datetime
from pathlib import Path

from bolus_classification import filter_primes

GLOOKO_DIR = Path(__file__).resolve().parent.parent / 'data' / 'glooko'


def _is_pen_source(serial):
    """Smart pen rows vs Dexcom manual-entry rows. Glooko tags the pen by its
    serial (e.g. ACS7HM); manual Dexcom rows have 'Dexcom' in the serial field."""
    s = serial.strip()
    return bool(s) and 'Dexcom' not in s


def load_glooko_bolus():
    """Return sorted [(datetime, units), ...] bolus injections from the smart pen.

    Empty list if the Glooko export is not present.
    """
    path = GLOOKO_DIR / 'Insulin data' / 'insulin_data_1.csv'
    if not path.exists():
        return []

    events = []
    with open(path, encoding='utf-8') as f:
        rows = list(csv.reader(f))

    for row in rows[2:]:  # skip metadata + header
        if len(row) < 5 or not row[0].strip():
            continue
        if not _is_pen_source(row[4]):
            continue
        val_str = row[2].strip()  # Samlet insulin column
        if not val_str:
            continue
        try:
            dt    = datetime.strptime(row[0].strip(), '%d/%m/%Y %H:%M')
            units = float(val_str.replace(',', '.'))
        except ValueError:
            continue
        events.append((dt, units))

    events.sort(key=lambda e: e[0])
    return filter_primes(events)


if __name__ == '__main__':
    events = load_glooko_bolus()
    print(f'Loaded {len(events)} bolus injections from Glooko export.')
    if events:
        print(f'Range: {events[0][0]} -> {events[-1][0]}')
        from collections import Counter
        by_month = Counter(dt.strftime('%Y-%m') for dt, _ in events)
        for m in sorted(by_month):
            total = sum(u for dt, u in events if dt.strftime('%Y-%m') == m)
            print(f'  {m}: {by_month[m]} injections, {total:.1f}u total')
