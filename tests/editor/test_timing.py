"""Speed curve mathematics. The identity these tests protect is the one everything else
downstream assumes: the integral of the rate equals the source span the clip consumes."""

import unittest

from takeone.editor.errors import ValidationError
from takeone.editor.timing import easing, retime
from takeone.editor.timing.curve import SpeedCurve, SpeedPoint

from tests.editor.support import ROOT  # noqa: F401

FRAME_30 = 1.0 / 30.0


class EasingAntiderivatives(unittest.TestCase):
    def test_analytic_area_matches_numeric_integration(self):
        for name in ("linear", "ease_in", "ease_out", "ease_in_out"):
            steps = 20000
            total = sum(easing.shape(name, (index + 0.5) / steps) for index in range(steps)) / steps
            self.assertAlmostEqual(easing.area(name, 1.0), total, places=5, msg=name)

    def test_area_starts_at_zero_and_is_monotonic(self):
        for name in easing.NAMES:
            control = (0.25, 0.1, 0.25, 1.0) if name == "bezier" else None
            self.assertEqual(easing.area(name, 0.0, control), 0.0)
            previous = -1.0
            for index in range(21):
                value = easing.area(name, index / 20.0, control)
                self.assertGreaterEqual(value + 1e-12, previous, msg=name)
                previous = value

    def test_bezier_control_abscissae_must_stay_monotonic(self):
        with self.assertRaises(ValidationError):
            easing.validate_bezier((1.4, 0.0, 0.2, 1.0))


class CurveIdentities(unittest.TestCase):
    def test_constant_rate_consumes_exactly_its_span(self):
        for rate in (0.25, 0.5, 1.0, 2.0, 4.0):
            curve = SpeedCurve.constant(3.0, rate)
            self.assertAlmostEqual(curve.source_duration_s, 3.0 * rate, places=9)

    def test_ramp_integral_matches_segment_sum(self):
        for slow in (0.2, 0.42, 0.8):
            curve = SpeedCurve.ramp(4.0, slow)
            segments = curve.segments()
            summed = sum((end - start) * rate for start, end, rate in segments)
            self.assertAlmostEqual(summed, curve.source_duration_s, places=9)

    def test_fitted_curve_consumes_the_requested_source_span(self):
        for span in (0.5, 1.0, 3.6, 9.0):
            curve = SpeedCurve.ramp(4.0, 0.42).fitted_to_source(span)
            self.assertAlmostEqual(curve.source_duration_s, span, places=9)

    def test_source_map_is_strictly_increasing(self):
        curve = SpeedCurve.ramp(4.0, 0.3)
        previous = -1.0
        for index in range(200):
            value = curve.source_offset_at(index * curve.duration_s / 199)
            self.assertGreater(value, previous)
            previous = value

    def test_inverse_map_round_trips(self):
        curve = SpeedCurve.ramp(5.0, 0.35)
        for index in range(1, 40):
            source = curve.source_duration_s * index / 40
            self.assertAlmostEqual(curve.source_offset_at(curve.timeline_time_at(source)), source, places=6)

    def test_every_easing_preserves_the_identity(self):
        for name in ("linear", "ease_in", "ease_out", "ease_in_out", "hold"):
            curve = SpeedCurve(
                (
                    SpeedPoint(0.0, 1.0),
                    SpeedPoint(1.5, 0.4, name),
                    SpeedPoint(3.0, 1.6, name),
                )
            )
            summed = sum((end - start) * rate for start, end, rate in curve.segments())
            self.assertAlmostEqual(summed, curve.source_duration_s, places=9, msg=name)


class CurveValidation(unittest.TestCase):
    def test_times_must_strictly_increase(self):
        with self.assertRaises(ValidationError):
            SpeedCurve((SpeedPoint(0.0, 1.0), SpeedPoint(0.0, 0.5)))

    def test_curve_must_start_at_zero(self):
        with self.assertRaises(ValidationError):
            SpeedCurve((SpeedPoint(0.4, 1.0), SpeedPoint(1.0, 0.5)))

    def test_rate_must_stay_positive(self):
        with self.assertRaises(ValidationError):
            SpeedPoint(1.0, 0.0)

    def test_a_curve_needs_two_points(self):
        with self.assertRaises(ValidationError):
            SpeedCurve((SpeedPoint(0.0, 1.0),))


class TimeMapApproximation(unittest.TestCase):
    def test_knots_stay_inside_a_quarter_frame(self):
        for slow in (0.15, 0.42, 0.9):
            curve = SpeedCurve.ramp(4.0, slow).fitted_to_source(3.0)
            knots, deviation = retime.time_map_knots(curve, FRAME_30)
            self.assertLessEqual(deviation, FRAME_30 * 0.25 + 1e-12, msg=f"slow={slow}")
            self.assertGreaterEqual(len(knots), 2)

    def test_expression_is_bounded_and_well_formed(self):
        curve = SpeedCurve.ramp(4.0, 0.42).fitted_to_source(3.0)
        knots, _ = retime.time_map_knots(curve, FRAME_30)
        expression = retime.setpts_expression(knots)
        self.assertEqual(expression.count("("), expression.count(")"))
        self.assertNotIn(";", expression)
        self.assertNotIn("'", expression)


if __name__ == "__main__":
    unittest.main()
