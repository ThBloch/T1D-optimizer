"""Glooko export loader for NovoPen 6 bolus events.

Reads `data/glooko/Insulin data/insulin_data_1.csv` and applies Glooko's
documented Prime Detection rule:

    An event is a PRIME iff (amount <= PRIME_MAX_U) AND (another insulin
    event follows within PRIME_WINDOW). Otherwise it is a real INJECTION.

Only events from the smart pen are kept; Dexcom-source rows (Thomas's
manual basal entries) are skipped - basal lives in Clarity.

Constants reflect Glooko's published rule (May 2026): >=2u within 6 min
of a following event = prime.
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path

GLOOKO_DIR   = Path(__file__).resolve().parent.parent / 'data' / 'glooko'
PRIME_MAX_U  = 2.0
PRIME_WINDOW = timedelta(minutes=6)


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

    bolus = []
    for i, (dt, u) in enumerate(events):
        if u <= PRIME_MAX_U:
            # Look both directions: same-timestamp ordering is arbitrary in the
            # CSV, so a small event may appear after its paired injection. Any
            # other pen event within +/-PRIME_WINDOW counts as a neighbor.
            is_prime = False
            for j in range(i - 1, -1, -1):
                if dt - events[j][0] > PRIME_WINDOW:
                    break
                is_prime = True
                break
            if not is_prime:
                for j in range(i + 1, len(events)):
                    if events[j][0] - dt > PRIME_WINDOW:
                        break
                    is_prime = True
                    break
            if is_prime:
                continue
        bolus.append((dt, u))
    return bolus


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
