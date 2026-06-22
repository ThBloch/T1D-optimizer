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


def _overnight_window(base=7.0, step_minutes=5):
    """Flat overnight CGM from 22:00 yesterday to 06:20 today at 5-min intervals."""
    yesterday = date.today() - timedelta(days=1)
    anchor = datetime(yesterday.year, yesterday.month, yesterday.day, 22, 0)
    end = datetime.combine(date.today(), time(6, 20))
    readings, dt = [], anchor
    while dt <= end:
        readings.append((dt, base))
        dt += timedelta(minutes=step_minutes)
    return readings


def _overnight_falling_second_half(step_minutes=5):
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
_DUMMY_CREDS  = {'username': 'x', 'password': 'x'}
_LIVE_READING = [(datetime.now().replace(second=0, microsecond=0), 7.0)]


class TestDexcomFetchSmoke(unittest.TestCase):

    def _run(self, window, whoop, extra_args=None, bolus=None):
        """Run dexcom_fetch.run() with stubs; return captured stdout.

        fetch_readings is stubbed to a single live reading (job 1 only).
        load_api_glucose returns the supplied overnight window (job 2).
        load_api_basal returns [] so --dose flag applies as anchor.
        """
        args = ['--dose', '20'] + (extra_args or [])
        buf = io.StringIO()
        fd, tmp_name = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        tmp = Path(tmp_name)
        tmp.unlink()
        try:
            with (
                patch.object(dexcom_fetch, 'load_creds',         return_value=_DUMMY_CREDS),
                patch.object(dexcom_fetch, 'fetch_readings',     return_value=_LIVE_READING),
                patch.object(dexcom_fetch, 'load_api_glucose',   return_value=window),
                patch.object(dexcom_fetch, 'load_api_basal',     return_value=[]),
                patch.object(dexcom_fetch, 'load_dexcom',        side_effect=FileNotFoundError),
                patch.object(dexcom_fetch, 'load_bolus_combined',return_value=bolus or []),
                patch.object(dexcom_fetch, 'load_whoop',         return_value=whoop),
                patch.object(dose_diary,   'DIARY_PATH',         tmp),
                patch('sys.stdout', buf),
            ):
                dexcom_fetch.run(args)
        finally:
            tmp.unlink(missing_ok=True)
        return buf.getvalue()

    def test_suggestion_produced_for_normal_night(self):
        out = self._run(_overnight_window(), _WHOOP_NORMAL)
        self.assertIn("Tonight's suggestion", out)
        self.assertIn('Suggested dose', out)

    def test_needs_strain_emitted_when_whoop_unavailable(self):
        out = self._run(_overnight_window(), whoop={}, extra_args=[])
        self.assertIn('NEEDS: strain', out)
        self.assertNotIn("Tonight's suggestion", out)

    def test_needs_dose_emitted_when_no_anchor(self):
        buf = io.StringIO()
        fd, tmp_name = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        tmp = Path(tmp_name)
        tmp.unlink()
        try:
            with (
                patch.object(dexcom_fetch, 'load_creds',         return_value=_DUMMY_CREDS),
                patch.object(dexcom_fetch, 'fetch_readings',     return_value=_LIVE_READING),
                patch.object(dexcom_fetch, 'load_api_glucose',   return_value=_overnight_window()),
                patch.object(dexcom_fetch, 'load_api_basal',     return_value=[]),
                patch.object(dexcom_fetch, 'load_dexcom',        side_effect=FileNotFoundError),
                patch.object(dexcom_fetch, 'load_bolus_combined',return_value=[]),
                patch.object(dexcom_fetch, 'load_whoop',         return_value=_WHOOP_NORMAL),
                patch.object(dose_diary,   'DIARY_PATH',         tmp),
                patch('sys.stdout', buf),
            ):
                dexcom_fetch.run([])  # no --dose flag, no API, no Clarity, empty diary
        finally:
            tmp.unlink(missing_ok=True)
        out = buf.getvalue()
        self.assertIn('NEEDS: dose', out)
        self.assertNotIn("Tonight's suggestion", out)

    def test_bolus_ambiguity_flagged_for_falling_slope(self):
        readings = _overnight_falling_second_half()
        yesterday = date.today() - timedelta(days=1)
        bolus_dt  = datetime(yesterday.year, yesterday.month, yesterday.day + 1, 3, 0)
        bolus     = [(bolus_dt, 2.0)]
        out = self._run(readings, _WHOOP_NORMAL, bolus=bolus)
        self.assertIn("Tonight's suggestion", out)
        self.assertIn('ambiguous', out)

    def test_api_basal_used_as_anchor_priority_1(self):
        """When API returns yesterday's dose, it should be used without --dose flag."""
        yesterday  = date.today() - timedelta(days=1)
        api_basal  = [(datetime(yesterday.year, yesterday.month, yesterday.day, 22, 0),
                       yesterday, 18.0)]
        buf = io.StringIO()
        fd, tmp_name = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        tmp = Path(tmp_name)
        tmp.unlink()
        try:
            with (
                patch.object(dexcom_fetch, 'load_creds',         return_value=_DUMMY_CREDS),
                patch.object(dexcom_fetch, 'fetch_readings',     return_value=_LIVE_READING),
                patch.object(dexcom_fetch, 'load_api_glucose',   return_value=_overnight_window()),
                patch.object(dexcom_fetch, 'load_api_basal',     return_value=api_basal),
                patch.object(dexcom_fetch, 'load_dexcom',        side_effect=FileNotFoundError),
                patch.object(dexcom_fetch, 'load_bolus_combined',return_value=[]),
                patch.object(dexcom_fetch, 'load_whoop',         return_value=_WHOOP_NORMAL),
                patch.object(dose_diary,   'DIARY_PATH',         tmp),
                patch('sys.stdout', buf),
            ):
                dexcom_fetch.run([])  # no --dose flag; API should supply it
        finally:
            tmp.unlink(missing_ok=True)
        out = buf.getvalue()
        self.assertIn("Tonight's suggestion", out)
        self.assertIn('API', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
