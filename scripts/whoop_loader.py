"""WHOOP data loader — reads from data/whoop_api/*.json (built by whoop_api_fetch.py).

I/O + parsing only. The cycle-to-local-date mapping lives in
`scripts/whoop_cycles.py` (P5).
"""
import json
from pathlib import Path

from whoop_cycles import cycle_date_for

API_DIR = Path(__file__).resolve().parent.parent / 'data' / 'whoop_api'


def load_whoop():
    """Return {date: {'date', 'strain', 'recovery', 'hrv', 'rhr', 'sleep_perf'}}."""
    cycles   = json.loads((API_DIR / 'cycles.json').read_text())['records']
    recovery = json.loads((API_DIR / 'recovery.json').read_text())['records']
    sleep    = json.loads((API_DIR / 'sleep.json').read_text())['records']

    rec_by_cycle = {r['cycle_id']: r for r in recovery}
    slp_by_cycle = {s['cycle_id']: s for s in sleep if not s.get('nap')}

    out = {}
    for c in cycles:
        score = c.get('score') or {}
        strain = score.get('strain')
        if strain is None:
            continue
        d = cycle_date_for(c)
        r_score = (rec_by_cycle.get(c['id']) or {}).get('score') or {}
        s_score = (slp_by_cycle.get(c['id']) or {}).get('score') or {}
        out[d] = {
            'date':       d,
            'strain':     round(float(strain), 2),
            'recovery':   r_score.get('recovery_score'),
            'hrv':        r_score.get('hrv_rmssd_milli'),
            'rhr':        r_score.get('resting_heart_rate'),
            'sleep_perf': s_score.get('sleep_performance_percentage'),
        }
    return out
