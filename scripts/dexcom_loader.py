"""Dexcom Clarity CSV loader.

Single source of truth for parsing Clarity exports (semicolon-delimited,
Danish locale, mmol/L with comma decimals). Imported by all analysis scripts.
"""
import csv, glob
from datetime import datetime, date
from collections import defaultdict
from pathlib import Path

DATA_DIR  = Path(__file__).resolve().parent.parent / 'data'
DIAGNOSIS = date(2025, 4, 9)

# Dexcom G7 measurable range; Clarity writes 'Høj'/'Lav' outside it.
GLUCOSE_HIGH_CLAMP = 22.2   # mmol/L (400 mg/dL)
GLUCOSE_LOW_CLAMP  = 2.2    # mmol/L (40 mg/dL)


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
                if not ts or 'T' not in ts or ts.startswith('Tidsstempel'):
                    continue
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    skipped_parse += 1
                    continue
                if dt.date() < DIAGNOSIS:
                    continue

                if etype == 'Estimeret glukoseværdi' and gval:
                    if gval == 'Høj':
                        glucose[dt] = GLUCOSE_HIGH_CLAMP
                    elif gval == 'Lav':
                        glucose[dt] = GLUCOSE_LOW_CLAMP
                    else:
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
        print(f'[dexcom_loader] skipped {skipped_parse} unparseable row(s) '
              f'(genuine malformed data - inspect export)')

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


def load_bolus_combined():
    """Bolus events merged across all sources, all dates.

    Clarity Hurtig rows are G7-app manual entries (regular pen days).
    Glooko ACS7HM rows are smart-pen NFC syncs (NovoPen 6 days). The two
    streams are disjoint by construction - manual entries never reach
    Glooko's pen-source rows, and smart-pen events never reach Clarity's
    raw CSV. No cutover or dedup needed.

    Emits a log-warn (does NOT filter) when a same-(minute, units)
    event appears in both streams - that would indicate the
    disjoint-by-construction assumption has broken (e.g. a future
    Glooko upgrade ingests G7-app data).

    Returns sorted [(datetime, units), ...].
    """
    from novopen_loader import load_glooko_bolus
    from bolus_classification import find_minute_unit_overlaps
    clarity = list(load_bolus_events())
    glooko  = list(load_glooko_bolus())
    overlaps = find_minute_unit_overlaps(clarity, glooko)
    if overlaps:
        print(f'[dexcom_loader] WARNING: {len(overlaps)} bolus event(s) appear '
              f'in BOTH Clarity and Glooko streams (matched on (minute, units)). '
              f'Streams previously disjoint by construction - investigate.')
        for dt, u in overlaps[:5]:
            print(f'  {dt} - {u}u')
        if len(overlaps) > 5:
            print(f'  ... and {len(overlaps) - 5} more')
    merged = clarity + glooko
    merged.sort(key=lambda e: e[0])
    return merged
