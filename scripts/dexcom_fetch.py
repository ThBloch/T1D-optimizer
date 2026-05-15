"""
dexcom_fetch.py — Daily glucose fetch for dose recommendation.
Pulls last 24h from Dexcom Share API (no CSV export needed).
Run: py -X utf8 dexcom_fetch.py
"""

import json, getpass
from datetime import datetime, timedelta, date
from pathlib import Path

from rules import thomas_rules
from dose_diary import load_diary, save_diary, find_row, upsert_row, parse_dose, DIARY_PATH
from whoop_loader import load_whoop

# ── CONFIG ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE   = PROJECT_ROOT / 'dexcom_creds.json'

HYPO_THR  = 4.0
TGT_LO    = 4.0   # TIR lower bound (matches rules_model.py)
TGT_HI    = 10.0  # TIR upper bound
OVN_START = 22    # basal injection hour (local)
OVN_END   = 7     # fasting/wake hour (local)

# ── CREDENTIALS ───────────────────────────────────────────────────────────────
def load_creds():
    if CREDS_FILE.exists():
        with open(CREDS_FILE, encoding='utf-8') as f:
            return json.load(f)
    print("No credentials file found. Enter Dexcom Share credentials.")
    print("(These are your Dexcom account login — not a follower account.)")
    username = input("Dexcom username (email): ").strip()
    password = getpass.getpass("Dexcom password: ")
    save = input("Save to dexcom_creds.json? (y/n): ").strip().lower()
    creds = {'username': username, 'password': password}
    if save == 'y':
        with open(CREDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(creds, f, indent=2)
        print(f"Saved to {CREDS_FILE}")
    return creds

# ── FETCH ─────────────────────────────────────────────────────────────────────
def fetch_readings(username, password):
    from pydexcom import Dexcom
    dex = Dexcom(username=username, password=password, region='ous')
    raw = dex.get_glucose_readings(minutes=1440, max_count=288)
    # pydexcom returns tz-aware local datetimes; strip tz for naive-datetime comparisons downstream
    return sorted([(r.datetime.replace(tzinfo=None), round(r.mmol_l, 1)) for r in raw],
                  key=lambda x: x[0])

# ── OVERNIGHT STATS ───────────────────────────────────────────────────────────
def overnight_stats(readings, inj_date):
    """Stats for overnight window: OVN_START on inj_date through OVN_END next day."""
    start = datetime(inj_date.year, inj_date.month, inj_date.day, OVN_START)
    end   = datetime(inj_date.year, inj_date.month, inj_date.day + 1, OVN_END)
    window = [(dt, v) for dt, v in readings if start <= dt <= end]
    if len(window) < 4:
        return None

    vals = [v for _, v in window]
    n    = len(vals)

    hypo_events, in_hypo = 0, False
    for v in vals:
        if v < HYPO_THR and not in_hypo:
            hypo_events += 1
            in_hypo = True
        elif v >= HYPO_THR:
            in_hypo = False

    tir = round(sum(1 for v in vals if TGT_LO <= v <= TGT_HI) / n * 100, 1)

    return {
        'inj_g':       vals[0],
        'fasting':     vals[-1],
        'mean':        round(sum(vals) / n, 1),
        'min_g':       min(vals),
        'tir':         tir,
        'hypo_events': hypo_events,
        'n_readings':  n,
    }

# ── MAIN ──────────────────────────────────────────────────────────────────────
def run():
    today     = date.today()
    yesterday = today - timedelta(days=1)

    print("Fetching Dexcom readings (region: OUS)...")
    creds    = load_creds()
    readings = fetch_readings(creds['username'], creds['password'])
    print(f"Fetched {len(readings)} readings covering last 24h.")

    if not readings:
        print("No readings returned. Check credentials and that Dexcom Share is enabled.")
        return

    latest_dt, latest_v = readings[-1]
    trend_note = f"  Current: {latest_v} mmol/L at {latest_dt.strftime('%H:%M')} ({latest_dt.date()})"

    stats = overnight_stats(readings, yesterday)

    if stats is None:
        print(f"\nNot enough readings for overnight window ({yesterday} {OVN_START}:00 -> {today} {OVN_END}:00).")
        print(f"Readings available: {len(readings)} — oldest: {readings[0][0].strftime('%H:%M %d-%m')}")
        print(trend_note)
        return

    print(f"\n--- Last night ({yesterday}) ---")
    print(f"  Injection-time glucose : {stats['inj_g']} mmol/L")
    print(f"  Fasting (07:00)        : {stats['fasting']} mmol/L")
    print(f"  Mean overnight         : {stats['mean']} mmol/L")
    print(f"  Min glucose            : {stats['min_g']} mmol/L")
    print(f"  TIR (4-10 mmol/L)      : {stats['tir']}%")
    print(f"  Hypo events (<4.0)     : {stats['hypo_events']}")
    print(f"  Readings in window     : {stats['n_readings']}")
    print(f"\n{trend_note}")

    diary = load_diary()
    upsert_row(diary, {
        'date':        str(yesterday),
        'fasting':     stats['fasting'],
        'hypo_events': stats['hypo_events'],
        'tir_pct':     stats['tir'],
    })

    yesterday_row = find_row(diary, yesterday)
    yesterday_dose = parse_dose(yesterday_row.get('dose_u'))

    if yesterday_dose is None:
        print()
        try:
            dose_str = input(f"Dose injected on {yesterday} (u): ").strip()
        except EOFError:
            print("Non-interactive run, no anchor dose on file -- skipping suggestion.")
            save_diary(diary)
            return
        yesterday_dose = parse_dose(dose_str)
        if yesterday_dose is None:
            print("Invalid input. Diary saved without anchor; suggestion skipped.")
            save_diary(diary)
            return
        yesterday_row['dose_u'] = yesterday_dose

    try:
        whoop = load_whoop()
        today_strain = (whoop.get(today) or {}).get('strain')
    except FileNotFoundError:
        today_strain = None
    if today_strain is None:
        print(f"\n  Today's WHOOP strain not yet on file (in-progress cycle).")

    dose, reasoning = thomas_rules(
        yesterday_dose=yesterday_dose,
        fasting=stats['fasting'],
        hypo_events=stats['hypo_events'],
        s1=today_strain,
    )

    upsert_row(diary, {
        'date':        str(today),
        'strain_s1':   today_strain if today_strain is not None else '',
        'suggested_u': dose,
        'reasoning':   ' | '.join(reasoning),
    })
    save_diary(diary)

    print(f"\n--- Tonight's suggestion ---")
    print(f"  Yesterday's dose: {yesterday_dose:.0f}u (from diary)")
    print(f"  Suggested dose : {dose}u")
    for r in reasoning:
        print(f"    * {r}")
    print(f"\n  Diary: {DIARY_PATH}")
    print()

if __name__ == '__main__':
    run()
