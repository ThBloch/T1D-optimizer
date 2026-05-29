"""Dexcom Clarity CSV loader.

Single source of truth for parsing Clarity exports (semicolon-delimited,
Danish locale, mmol/L with comma decimals). Imported by all analysis scripts.
"""
import csv, glob, os
from datetime import datetime, date
from collections import defaultdict
from pathlib import Path

DATA_DIR  = Path(__file__).resolve().parent.parent / 'data'
DIAGNOSIS = date(2025, 4, 9)

# Bolus sources cut over at this date: Clarity (manual G7 logs) is reliable
# before; Glooko/NovoPen 6 picks up from 2026-01-31 onwards.
NOVOPEN_CUTOVER = date(2026, 1, 31)


def load_dexcom():
    """Read all Clarity_*.csv exports under DATA_DIR and return three structures.

    Returns:
      glucose_list : sorted [(datetime, mmol/L), ...]
      basal_list   : sorted [(injection_dt, date, units), ...] one entry per date
      bolus_by_date: defaultdict[date -> total_units]
    """
    files = sorted(glob.glob(str(DATA_DIR / 'Clarity_*.csv')))
    glucose  = {}
    basal_ts = {}
    bolus_ts = set()
    skipped_parse = 0

    for path in files:
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.reader(f, delimiter=';'):
                if len(row) < 9:
                    continue
                ts    = row[1].strip().strip('"')
                etype = row[2].strip().strip('"')
                esub  = row[3].strip().strip('"')
                gval  = row[7].strip().strip('"')
                ival  = row[8].strip().strip('"')
                if not ts or 'T' not in ts:
                    continue
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    skipped_parse += 1
                    continue
                if dt.date() < DIAGNOSIS:
                    continue

                if etype == 'Estimeret glukoseværdi' and gval:
                    try:
                        glucose[dt] = float(gval.replace(',', '.'))
                    except ValueError:
                        skipped_parse += 1

                if etype == 'Insulin' and ival:
                    try:
                        units = float(ival.replace(',', '.'))
                    except ValueError:
                        skipped_parse += 1
                        continue
                    if 'Lang' in esub:
                        if dt not in basal_ts:
                            basal_ts[dt] = units
                    elif 'Hurtig' in esub:
                        bolus_ts.add((dt, units))

    if skipped_parse:
        print(f'[dexcom_loader] skipped {skipped_parse} rows due to parse errors '
              f'(check Clarity export locale/format)')

    basal_by_date = {}
    for dt, units in sorted(basal_ts.items()):
        d = dt.date()
        if d not in basal_by_date:
            basal_by_date[d] = [dt, units]
        else:
            basal_by_date[d][1] += units

    bolus = defaultdict(float)
    for dt, units in bolus_ts:
        bolus[dt.date()] += units

    glucose_list = sorted(glucose.items())
    basal_list   = sorted([(v[0], d, v[1]) for d, v in basal_by_date.items()])
    return glucose_list, basal_list, bolus


def load_bolus_events():
    """Return sorted list of deduplicated individual bolus events.

    Returns:
      [(datetime, units), ...] sorted by timestamp, deduplicated by timestamp.

    Parses the same Clarity CSV files as load_dexcom(). Use when you need
    event-level timestamps (e.g. bolus in window before injection).
    """
    files = sorted(glob.glob(str(DATA_DIR / 'Clarity_*.csv')))
    events = {}   # dt -> units, first-seen wins (dedup across overlapping exports)
    for path in files:
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.reader(f, delimiter=';'):
                if len(row) < 9:
                    continue
                ts    = row[1].strip().strip('"')
                etype = row[2].strip().strip('"')
                esub  = row[3].strip().strip('"')
                ival  = row[8].strip().strip('"')
                if not ts or 'T' not in ts:
                    continue
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    continue
                if dt.date() < DIAGNOSIS:
                    continue
                if etype == 'Insulin' and ival and 'Hurtig' in esub:
                    try:
                        u = float(ival.replace(',', '.'))
                    except ValueError:
                        continue
                    if dt not in events:
                        events[dt] = u
    return sorted(events.items())


def load_bolus_combined(cutover_date=NOVOPEN_CUTOVER):
    """Bolus events from Clarity (pre-cutover) + Glooko/NovoPen (post-cutover).

    Returns sorted [(datetime, units), ...]. Clarity supplies events strictly
    before `cutover_date`; Glooko supplies events on or after.
    """
    from novopen_loader import load_glooko_bolus
    clarity = load_bolus_events()
    glooko  = load_glooko_bolus()
    merged  = [(dt, u) for dt, u in clarity if dt.date() < cutover_date]
    merged += [(dt, u) for dt, u in glooko  if dt.date() >= cutover_date]
    merged.sort(key=lambda e: e[0])
    return merged
