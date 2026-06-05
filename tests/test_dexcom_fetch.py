"""Smoke tests for the dexcom_fetch.run() production path.

No live API calls; all external dependencies are stubbed. Tests verify
that the fetch -> night_stats -> rules -> diary pipeline is wired correctly.

Run from project root:
    py -X utf8 tests/test_dexcom_fetch.py
"""
import io, os, sys, tempfile, unittest
from datetime import datetime, timedelta, date, time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

import dexcom_fetch
import dose_diary


def _cgm_flat(base=7.0, step_minutes=5):
    """Flat overnight CGM from 22:00 yesterday to 06:20 today at 5-min intervals."""
    yesterday = date.today() - timedelta(days=1)
    anchor = datetime(yesterday.year, yesterday.month, yesterday.day, 22, 0)
    end = datetime.combine(date.today(), time(6, 20))
    readings, dt = [], anchor
    while dt <= end:
        readings.append((dt, base))
        dt += timedelta(minutes=step_minutes)
    return readings


def _cgm_falling_second_half(step_minutes=5):
    """First half flat at 8.0; second half declining to 4.5 to force a negative slope."""
    yesterday = date.today() - timedelta(days=1)
    anchor = datetime(yesterday.year, yesterday.month, yesterday.day, 22, 0)
    end = datetime.combine(date.today(), time(6, 20))
    all_dts, dt = [], anchor
    while dt <= end:
        all_dts.append(dt)
        dt += timedelta(minutes=step_minutes)
    n = len(all_dts)
    split = n // 2
    readings = []
    for i, t in enumerate(all_dts):
        if i < split:
            readings.append((t, 8.0))
        else:
            frac = (i - split) / max(n - split - 1, 1)
            readings.append((t, round(8.0 - 3.5 * frac, 1)))
    return readings


_TODAY = date.today()
_WHOOP_NORMAL = {_TODAY: {'strain': 10.0}}
_DUMMY_CREDS = {'username': 'x', 'password': 'x'}


class TestDexcomFetchSmoke(unittest.TestCase):

    def _run(self, readings, whoop, extra_args=None, bolus=None):
        """Run dexcom_fetch.run() with stubs; return captured stdout."""
        args = ['--dose', '20'] + (extra_args or [])
        buf = io.StringIO()
        fd, tmp_name = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        tmp = Path(tmp_name)
        tmp.unlink()  # remove so load_diary returns [] (no existing diary)
        try:
            with (
                patch.object(dexcom_fetch, 'load_creds', return_value=_DUMMY_CREDS),
                patch.object(dexcom_fetch, 'fetch_readings', return_value=readings),
                patch.object(dexcom_fetch, 'load_dexcom', side_effect=FileNotFoundError),
                patch.object(dexcom_fetch, 'load_bolus_combined', return_value=bolus or []),
                patch.object(dexcom_fetch, 'load_whoop', return_value=whoop),
                patch.object(dose_diary, 'DIARY_PATH', tmp),
                patch('sys.stdout', buf),
            ):
                dexcom_fetch.run(args)
        finally:
            tmp.unlink(missing_ok=True)
        return buf.getvalue()

    def test_suggestion_produced_for_normal_night(self):
        out = self._run(_cgm_flat(), _WHOOP_NORMAL)
        self.assertIn("Tonight's suggestion", out)
        self.assertIn('Suggested dose', out)

    def test_needs_strain_emitted_when_whoop_unavailable(self):
        out = self._run(_cgm_flat(), whoop={}, extra_args=[])
        self.assertIn('NEEDS: strain', out)
        self.assertNotIn("Tonight's suggestion", out)

    def test_bolus_ambiguity_flagged_for_falling_slope(self):
        readings = _cgm_falling_second_half()
        # Place a bolus event in the second half of the overnight window
        yesterday = date.today() - timedelta(days=1)
        bolus_dt = datetime(yesterday.year, yesterday.month, yesterday.day + 1, 3, 0)
        bolus = [(bolus_dt, 2.0)]
        out = self._run(readings, _WHOOP_NORMAL, bolus=bolus)
        self.assertIn("Tonight's suggestion", out)
        self.assertIn('ambiguous', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
