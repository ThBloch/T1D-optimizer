"""Unit tests for the production decision rule.

Run from project root:
    py -X utf8 -m unittest tests.test_rules -v
Or directly:
    py -X utf8 tests/test_rules.py
"""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from rules import thomas_rules, DOSE_MIN, DOSE_MAX


class TestThomasRules(unittest.TestCase):

    def test_none_anchor_returns_none(self):
        dose, reasoning = thomas_rules(None, 8.0, 0, 5.0)
        self.assertIsNone(dose)
        self.assertIn('No anchor', reasoning[0])

    def test_fasting_in_range_no_change(self):
        dose, _ = thomas_rules(20, 7.0, 0, 5.0)
        self.assertEqual(dose, 20)

    def test_fasting_just_above_lo_plus_one(self):
        dose, _ = thomas_rules(20, 10.6, 0, 5.0)
        self.assertEqual(dose, 21)

    def test_fasting_at_lo_boundary_no_change(self):
        # Strict greater-than: 10.0 exactly is NOT > 10.0
        dose, _ = thomas_rules(20, 10.0, 0, 5.0)
        self.assertEqual(dose, 20)

    def test_fasting_mid_tier_plus_two(self):
        dose, _ = thomas_rules(20, 13.0, 0, 5.0)
        self.assertEqual(dose, 22)

    def test_fasting_at_mid_boundary_stays_low_tier(self):
        # 12.0 exactly is not > 12.0, so falls to lo tier (+1u)
        dose, _ = thomas_rules(20, 12.0, 0, 5.0)
        self.assertEqual(dose, 21)

    def test_fasting_very_high_plus_three(self):
        dose, _ = thomas_rules(20, 15.0, 0, 5.0)
        self.assertEqual(dose, 23)

    def test_one_hypo_minus_one(self):
        dose, _ = thomas_rules(20, 8.0, 1, 5.0)
        self.assertEqual(dose, 19)

    def test_multiple_hypos_minus_two(self):
        dose, _ = thomas_rules(20, 8.0, 3, 5.0)
        self.assertEqual(dose, 18)

    def test_hypo_overrides_high_fasting(self):
        # Hypo takes priority over fasting tier; +3 fasting adjustment must NOT apply
        dose, reasoning = thomas_rules(20, 15.0, 1, 5.0)
        self.assertEqual(dose, 19)
        self.assertFalse(any('15.0' in r for r in reasoning))

    def test_activity_stacks_on_glucose(self):
        # High fasting (+2) plus high strain (-2) -> net zero adjustment
        dose, _ = thomas_rules(20, 13.0, 0, 14.0)
        self.assertEqual(dose, 20)

    def test_activity_below_threshold_no_effect(self):
        dose, _ = thomas_rules(20, 8.0, 0, 11.9)
        self.assertEqual(dose, 20)

    def test_activity_at_threshold_applies(self):
        # >= 12.0, so 12.0 exactly counts
        dose, _ = thomas_rules(20, 8.0, 0, 12.0)
        self.assertEqual(dose, 18)

    def test_clamp_upper_bound(self):
        # 28 + 3 = 31, clamped to DOSE_MAX
        dose, reasoning = thomas_rules(28, 15.0, 0, 5.0)
        self.assertEqual(dose, DOSE_MAX)
        self.assertTrue(any('Clamped' in r for r in reasoning))

    def test_clamp_lower_bound(self):
        # 16 - 2 (hypos) - 2 (activity) = 12, clamped to DOSE_MIN
        dose, reasoning = thomas_rules(16, 8.0, 2, 14.0)
        self.assertEqual(dose, DOSE_MIN)
        self.assertTrue(any('Clamped' in r for r in reasoning))

    def test_none_strain_treated_as_no_activity(self):
        dose, _ = thomas_rules(20, 8.0, 0, None)
        self.assertEqual(dose, 20)

    def test_none_fasting_with_no_hypo_no_change(self):
        dose, _ = thomas_rules(20, None, 0, 5.0)
        self.assertEqual(dose, 20)

    def test_custom_threshold_param_lowers_trigger(self):
        # Override fasting_lo to 8.0; fasting of 9.0 now triggers +1u
        dose, _ = thomas_rules(20, 9.0, 0, 5.0, fasting_lo=8.0)
        self.assertEqual(dose, 21)

    def test_new_pen_minus_one(self):
        dose, reasoning = thomas_rules(20, 8.0, 0, 5.0, new_pen=True)
        self.assertEqual(dose, 19)
        self.assertTrue(any('New pen' in r for r in reasoning))

    def test_new_pen_default_false(self):
        # Explicit baseline: no new_pen -> no adjustment
        dose, _ = thomas_rules(20, 8.0, 0, 5.0)
        self.assertEqual(dose, 20)

    def test_new_pen_stacks_with_glucose_and_activity(self):
        # +1 fasting tier + -2 activity + -1 new pen = -2 net
        dose, _ = thomas_rules(20, 11.0, 0, 13.0, new_pen=True)
        self.assertEqual(dose, 18)

    # ── SLOPE-BASED TIER ──────────────────────────────────────────────────────

    def test_slope_in_flat_band_no_change(self):
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=0.1)
        self.assertEqual(dose, 20)

    def test_slope_just_above_flat_plus_one(self):
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=0.5)
        self.assertEqual(dose, 21)

    def test_slope_at_flat_boundary_no_change(self):
        # Strict greater-than: 0.3 exactly is NOT > 0.3
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=0.3)
        self.assertEqual(dose, 20)

    def test_slope_at_mid_boundary_stays_low_tier(self):
        # 0.7 exactly is not > 0.7, so falls to lo tier (+1u)
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=0.7)
        self.assertEqual(dose, 21)

    def test_slope_mid_tier_plus_two(self):
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=1.0)
        self.assertEqual(dose, 22)

    def test_slope_at_hi_boundary_stays_mid_tier(self):
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=1.2)
        self.assertEqual(dose, 22)

    def test_slope_above_hi_plus_three(self):
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=1.5)
        self.assertEqual(dose, 23)

    def test_slope_just_below_flat_minus_one(self):
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=-0.5)
        self.assertEqual(dose, 19)

    def test_slope_at_down_boundary_no_change(self):
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=-0.3)
        self.assertEqual(dose, 20)

    def test_slope_below_negative_hi_minus_two(self):
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=-1.5)
        self.assertEqual(dose, 18)

    def test_slope_capped_at_minus_two_even_for_extreme_drop(self):
        # No -3u tier on the down side (asymmetric magnitude per Q1 decision)
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=-5.0)
        self.assertEqual(dose, 18)

    def test_hypo_overrides_steep_slope(self):
        # hypo_events=1 must win over slope=+1.5 (which would otherwise be +3u)
        dose, reasoning = thomas_rules(20, None, 1, 5.0, sh_slope=1.5)
        self.assertEqual(dose, 19)
        self.assertFalse(any('Slope' in r for r in reasoning))

    def test_slope_overrides_fasting_when_both_provided(self):
        # Steep slope must trigger; fasting in range should NOT be evaluated
        dose, reasoning = thomas_rules(20, 7.0, 0, 5.0, sh_slope=1.5)
        self.assertEqual(dose, 23)
        self.assertFalse(any('Fasting' in r or 'fasting' in r for r in reasoning))

    def test_slope_stacks_with_activity(self):
        # +1 from slope + -2 from activity = -1 net
        dose, _ = thomas_rules(20, None, 0, 14.0, sh_slope=0.5)
        self.assertEqual(dose, 19)

    def test_slope_none_falls_back_to_fasting(self):
        # Regression: existing fasting fallback still works when no slope provided
        dose, reasoning = thomas_rules(20, 11.0, 0, 5.0)
        self.assertEqual(dose, 21)
        self.assertTrue(any('fallback' in r for r in reasoning))

    def test_slope_and_fasting_both_none_no_glucose_adj(self):
        dose, _ = thomas_rules(20, None, 0, 5.0)
        self.assertEqual(dose, 20)

    def test_custom_slope_thresholds(self):
        # Override slope_flat to 0.2; slope of 0.25 now triggers +1u
        dose, _ = thomas_rules(20, None, 0, 5.0, sh_slope=0.25, slope_flat=0.2)
        self.assertEqual(dose, 21)


if __name__ == '__main__':
    unittest.main(verbosity=2)
