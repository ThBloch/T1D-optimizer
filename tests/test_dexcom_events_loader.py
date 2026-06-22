"""Unit tests for scripts/dexcom_events_loader.py.

Run from project root:
    py -X utf8 -m unittest tests.test_dexcom_events_loader -v
Or directly:
    py -X utf8 tests/test_dexcom_events_loader.py
"""
import sys, unittest
from datetime import datetime, date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from dexcom_events_loader import (
    _to_naive_local,
    load_api_basal,
    load_api_bolus,
    load_api_glucose,
)

MODULE = 'dexcom_events_loader'


def _evt(sub, value, display_time, status='created'):
    return {
        'recordId': f'id-{sub}-{display_time}',
        'eventSubType': sub,
        'eventStatus': status,
        'value': value,
        'displayTime': display_time,
        'systemTime': '2026-01-01T00:00:00Z',
    }


def _egv(value, display_time):
    return {
        'recordId': f'egv-{display_time}',
        'value': value,
        'unit': 'mg/dL',
        'displayTime': display_time,
        'systemTime': '2026-01-01T00:00:00Z',
    }


class TestToNaiveLocal(unittest.TestCase):

    def test_full_offset_with_microseconds(self):
        dt = _to_naive_local('2026-06-21T08:16:54.484+02:00')
        self.assertEqual(dt, datetime(2026, 6, 21, 8, 16, 54, 484000))

    def test_no_seconds_offset(self):
        dt = _to_naive_local('2026-06-20T01:00+02:00')
        self.assertEqual(dt, datetime(2026, 6, 20, 1, 0))

    def test_dst_transition_odd_offset(self):
        # +01:59:59 appears for records at DST boundary in the API.
        dt = _to_naive_local('2025-04-26T06:30:00.358+01:59:59')
        self.assertEqual(dt, datetime(2025, 4, 26, 6, 30, 0, 358000))

    def test_utc_z_suffix(self):
        dt = _to_naive_local('2026-01-01T12:00:00Z')
        self.assertEqual(dt, datetime(2026, 1, 1, 12, 0, 0))


class TestLoadApiBasal(unittest.TestCase):

    def test_returns_long_acting_only(self):
        records = [
            _evt('longActing', '17.00', '2026-06-20T23:13:38.887+02:00'),
            _evt('fastActing', '3.00',  '2026-06-20T12:00:00+02:00'),
        ]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_basal()
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][2], 17.0)

    def test_deleted_status_skipped(self):
        records = [
            _evt('longActing', '17.00', '2026-06-20T23:00:00+02:00', status='deleted'),
            _evt('longActing', '15.00', '2026-06-19T23:00:00+02:00'),
        ]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_basal()
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][2], 15.0)

    def test_updated_status_included(self):
        records = [
            _evt('longActing', '18.00', '2026-06-20T23:00:00+02:00', status='updated'),
        ]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_basal()
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][2], 18.0)

    def test_same_day_units_summed(self):
        records = [
            _evt('longActing', '15.00', '2026-06-20T22:00:00+02:00'),
            _evt('longActing', '2.00',  '2026-06-20T23:30:00+02:00'),
        ]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_basal()
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][2], 17.0)

    def test_same_day_inj_dt_is_earliest(self):
        records = [
            _evt('longActing', '15.00', '2026-06-20T23:30:00+02:00'),
            _evt('longActing', '2.00',  '2026-06-20T22:00:00+02:00'),
        ]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_basal()
        self.assertEqual(result[0][0], datetime(2026, 6, 20, 22, 0, 0))

    def test_date_field_is_local_date(self):
        records = [_evt('longActing', '17.00', '2026-06-20T23:00:00+02:00')]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_basal()
        self.assertEqual(result[0][1], date(2026, 6, 20))

    def test_sorted_ascending(self):
        records = [
            _evt('longActing', '15.00', '2026-06-21T23:00:00+02:00'),
            _evt('longActing', '17.00', '2026-06-20T23:00:00+02:00'),
        ]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_basal()
        self.assertLess(result[0][1], result[1][1])

    def test_empty_cache_returns_empty(self):
        with patch(f'{MODULE}._load_events_cache', return_value=[]):
            self.assertEqual(load_api_basal(), [])


class TestLoadApiBolus(unittest.TestCase):

    def test_returns_fast_acting_only(self):
        records = [
            _evt('fastActing', '3.00',  '2026-06-20T12:00:00+02:00'),
            _evt('longActing', '17.00', '2026-06-20T23:00:00+02:00'),
        ]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_bolus()
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][1], 3.0)

    def test_deleted_status_skipped(self):
        records = [
            _evt('fastActing', '3.00', '2026-06-20T12:00:00+02:00', status='deleted'),
            _evt('fastActing', '4.00', '2026-06-20T18:00:00+02:00'),
        ]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_bolus()
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][1], 4.0)

    def test_sorted_ascending(self):
        records = [
            _evt('fastActing', '4.00', '2026-06-20T18:00:00+02:00'),
            _evt('fastActing', '3.00', '2026-06-20T12:00:00+02:00'),
        ]
        with patch(f'{MODULE}._load_events_cache', return_value=records):
            result = load_api_bolus()
        self.assertLess(result[0][0], result[1][0])

    def test_empty_cache_returns_empty(self):
        with patch(f'{MODULE}._load_events_cache', return_value=[]):
            self.assertEqual(load_api_bolus(), [])


class TestLoadApiGlucose(unittest.TestCase):

    START = datetime(2026, 6, 20, 22, 0, 0)
    END   = datetime(2026, 6, 21, 6, 20, 0)

    def test_mg_dl_to_mmol_conversion(self):
        records = [_egv(180, '2026-06-21T02:00:00+02:00')]  # 180/18.0182 = 9.99... -> 10.0
        with patch(f'{MODULE}._load_egvs_cache', return_value=records):
            result = load_api_glucose(self.START, self.END)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][1], round(180 / 18.0182, 1))

    def test_known_value_81_is_4point5(self):
        # 81 mg/dL / 18.0182 = 4.496 -> 4.5 mmol/L
        records = [_egv(81, '2026-06-21T02:00:00+02:00')]
        with patch(f'{MODULE}._load_egvs_cache', return_value=records):
            result = load_api_glucose(self.START, self.END)
        self.assertAlmostEqual(result[0][1], 4.5)

    def test_window_filtering_excludes_outside(self):
        records = [
            _egv(90,  '2026-06-20T21:55:00+02:00'),  # before start -> excluded
            _egv(100, '2026-06-20T22:00:00+02:00'),  # on start boundary -> included
            _egv(110, '2026-06-21T03:00:00+02:00'),  # inside -> included
            _egv(120, '2026-06-21T06:20:00+02:00'),  # on end boundary -> included
            _egv(130, '2026-06-21T06:25:00+02:00'),  # after end -> excluded
        ]
        with patch(f'{MODULE}._load_egvs_cache', return_value=records):
            result = load_api_glucose(self.START, self.END)
        self.assertEqual(len(result), 3)

    def test_sorted_ascending(self):
        records = [
            _egv(110, '2026-06-21T04:00:00+02:00'),
            _egv(100, '2026-06-21T02:00:00+02:00'),
        ]
        with patch(f'{MODULE}._load_egvs_cache', return_value=records):
            result = load_api_glucose(self.START, self.END)
        self.assertLess(result[0][0], result[1][0])

    def test_empty_cache_returns_empty(self):
        with patch(f'{MODULE}._load_egvs_cache', return_value=[]):
            self.assertEqual(load_api_glucose(self.START, self.END), [])

    def test_returns_mmol_rounded_to_one_decimal(self):
        records = [_egv(100, '2026-06-21T02:00:00+02:00')]
        with patch(f'{MODULE}._load_egvs_cache', return_value=records):
            result = load_api_glucose(self.START, self.END)
        # Result should be rounded to 1 decimal place
        self.assertEqual(result[0][1], round(100 / 18.0182, 1))


if __name__ == '__main__':
    unittest.main()
