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
                    continue
                if dt.date() < DIAGNOSIS:
                    continue

                if etype == 'Estimeret glukoseværdi' and gval:
                    try:
                        glucose[dt] = float(gval.replace(',', '.'))
                    except ValueError:
                        pass

                if etype == 'Insulin' and ival:
                    try:
                        units = float(ival.replace(',', '.'))
                    except ValueError:
                        continue
                    if 'Lang' in esub:
                        if dt not in basal_ts:
                            basal_ts[dt] = units
                    elif 'Hurtig' in esub:
                        bolus_ts.add((dt, units))

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
