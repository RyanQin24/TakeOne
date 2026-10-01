"""Synthetic geometry checks for Photo Scout's design; not a reconstruction engine.

Only Python's standard library is required. No images, networks, model weights,
robot APIs, or hardware are used. Every number in the report is authored test data.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Camera:
    fx: float = 1000.0
    fy: float = 1000.0
    cx: float = 640.0
    cy: float = 360.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.fx, self.fy, self.cx, self.cy)):
            raise ValueError("Intrinsics must be finite")
        if min(self.fx, self.fy) <= 0:
            raise ValueError("Focal lengths must be positive")

    def project(self, point: tuple[float, float, float]) -> tuple[float, float]:
        x, y, z = point
        if not all(math.isfinite(v) for v in point) or z <= 0:
            raise ValueError("Projection requires a finite point in front of the camera")
        return self.fx * x / z + self.cx, self.fy * y / z + self.cy

    def unproject(self, pixel: tuple[float, float], axial_depth: float) -> tuple[float, float, float]:
        if not all(math.isfinite(v) for v in (*pixel, axial_depth)) or axial_depth <= 0:
            raise ValueError("Pixel and axial depth must be finite; depth must be positive")
        u, v = pixel
        return ((u - self.cx) * axial_depth / self.fx,
                (v - self.cy) * axial_depth / self.fy, axial_depth)


def dot(a: tuple, b: tuple) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def cv_to_level_world(p: tuple[float, float, float]) -> tuple[float, float, float]:
    """Example *level* registration: right -> +X, forward -> +Y, down -> -Z.

    Real captures require measured/estimated orientation; this is not a universal
    EXIF-independent transform. Translation is deliberately separate.
    """
    return p[0], p[2], -p[1]


def floor_intersection(origin: tuple, direction: tuple, normal=(0.0, 0.0, 1.0), offset=0.0) -> tuple:
    """Intersect a ray with n.p + offset = 0; reject ambiguous/behind-camera rays."""
    if not all(math.isfinite(v) for v in (*origin, *direction, *normal, offset)):
        raise ValueError("Nonfinite plane/ray")
    norm_product = math.sqrt(dot(normal, normal) * dot(direction, direction))
    denominator = dot(normal, direction)
    if norm_product == 0 or abs(denominator) <= 1e-8 * norm_product:
        raise ValueError("Ray nearly parallel to plane")
    t = -(dot(normal, origin) + offset) / denominator
    if t <= 0:
        raise ValueError("Intersection is behind the camera")
    return tuple(a + t * b for a, b in zip(origin, direction, strict=True))


def fit_scale(predicted_lengths: list[float], measured_lengths: list[float], weights: list[float]) -> float:
    if not predicted_lengths or not len(predicted_lengths) == len(measured_lengths) == len(weights):
        raise ValueError("Nonempty matching anchor arrays are required")
    if any(not math.isfinite(v) or v <= 0 for v in predicted_lengths + measured_lengths + weights):
        raise ValueError("Lengths and weights must be positive and finite")
    return sum(w * d * length for d, length, w in zip(predicted_lengths, measured_lengths, weights)) / sum(
        w * d * d for d, w in zip(predicted_lengths, weights))


def source_depth_support(projected_z: float, source_z: float | None, tolerance: float) -> bool:
    """Toy axial-depth gate only; production also needs masks/IDs/visibility/normals."""
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Tolerance must be finite and nonnegative")
    return (source_z is not None and math.isfinite(source_z) and math.isfinite(projected_z)
            and min(source_z, projected_z) > 0 and abs(projected_z - source_z) <= tolerance)


def conditional_clearance(sample_min: float, error_bound: float | None, speed_bound: float, gap_s: float) -> float | None:
    """Conditional Lipschitz bound with endpoint samples and complete bounded models.

    None denotes absent geometry/error bounds, NOT infinity or clear space.
    This is not an estimate of real robot clearance or a safety probability.
    """
    if not math.isfinite(sample_min) or any(not math.isfinite(v) or v < 0 for v in (speed_bound, gap_s)):
        raise ValueError("Invalid sampled-distance or temporal bound")
    if error_bound is None:
        return None
    if not math.isfinite(error_bound) or error_bound < 0:
        raise ValueError("Invalid geometric error bound")
    return sample_min - error_bound - speed_bound * gap_s / 2


class GeometryProof(unittest.TestCase):
    def test_01_depth_roundtrip(self):
        camera = Camera()
        self.assertEqual(camera.unproject(camera.project((1.0, -0.5, 2.0)), 2.0), (1.0, -0.5, 2.0))

    def test_02_random_roundtrips(self):
        rng, camera = random.Random(17), Camera(903, 917, 502, 391)
        for _ in range(200):
            p = (rng.uniform(-2, 2), rng.uniform(-2, 2), rng.uniform(0.3, 8))
            for a, b in zip(p, camera.unproject(camera.project(p), p[2])):
                self.assertAlmostEqual(a, b, places=11)

    def test_03_scale_is_invisible_in_source_projection(self):
        camera, p = Camera(), (0.4, -0.2, 2.0)
        for s in (0.3, 1.3, 5):
            for a, b in zip(camera.project(p), camera.project(tuple(s * x for x in p))):
                self.assertAlmostEqual(a, b)

    def test_04_translated_camera_exposes_scale_error(self):
        c = Camera()
        true_u = c.project((-0.3, 0.0, 2.0))[0]
        wrong_u = c.project((-0.3, 0.0, 2.6))[0]
        self.assertAlmostEqual(abs(true_u - wrong_u), 34.61538461538464)

    def test_05_single_scale_anchor(self):
        self.assertAlmostEqual(fit_scale([0.91], [0.7], [1]), 1 / 1.3)

    def test_06_multiple_scale_anchors(self):
        self.assertAlmostEqual(fit_scale([0.91, 1.3, 2.6], [0.7, 1, 2], [1, 2, 1]), 1 / 1.3)

    def test_07_bad_anchors_rejected(self):
        for lengths in ([], [0], [-1], [float('nan')]):
            with self.assertRaises(ValueError):
                fit_scale(lengths, [1], [1])

    def test_08_axial_depth_is_not_range(self):
        p = Camera().unproject((1640, 360), 2)
        self.assertEqual(p, (2, 0, 2))
        self.assertAlmostEqual(math.sqrt(dot(p, p)), math.sqrt(8))

    def test_09_floor_hit(self):
        self.assertEqual(floor_intersection((0, 0, 1.5), (0, 1, -0.5)), (0, 3, 0))

    def test_10_parallel_floor_rejected(self):
        with self.assertRaises(ValueError):
            floor_intersection((0, 0, 1.5), (1, 0, 0))

    def test_11_behind_camera_rejected(self):
        with self.assertRaises(ValueError):
            floor_intersection((0, 0, 1.5), (0, 1, 0.5))

    def test_12_coordinate_axes(self):
        self.assertEqual(cv_to_level_world((1, 0, 0)), (1, 0, 0))
        self.assertEqual(cv_to_level_world((0, 1, 0)), (0, 0, -1))
        self.assertEqual(cv_to_level_world((0, 0, 1)), (0, 1, 0))

    def test_13_rotation_preserves_metric_lengths(self):
        p = (1, 2, 3)
        self.assertEqual(dot(p, p), dot(cv_to_level_world(p), cv_to_level_world(p)))

    def test_14_lateral_parallax(self):
        near_shift, far_shift = -1000 * 0.3 / 2, -1000 * 0.3 / 5
        self.assertAlmostEqual(abs(near_shift - far_shift), 90)

    def test_15_zoom_does_not_make_depth_dependent_parallax(self):
        near, far = (0, 0, 2), (0, 0, 5)
        for focal in (800, 1000, 1300):
            self.assertEqual(Camera(focal, focal).project(near), Camera(focal, focal).project(far))

    def test_16_nearfield_depth_sensitivity(self):
        near, far = 1000 * 0.3 / 1**2, 1000 * 0.3 / 5**2
        self.assertAlmostEqual(near / far, 25)

    def test_17_sensitivity_matches_finite_difference(self):
        f, b, z, eps = 1000, 0.3, 3, 1e-6
        difference = ((-f * b / (z + eps)) - (-f * b / (z - eps))) / (2 * eps)
        self.assertAlmostEqual(difference, f * b / z**2, places=5)

    def test_18_unknown_depth_never_supported(self):
        self.assertFalse(source_depth_support(2, None, 0.01))
        self.assertFalse(source_depth_support(2, float('inf'), 0.01))

    def test_19_behind_observed_surface_not_supported(self):
        self.assertFalse(source_depth_support(2, 1, 0.01))
        self.assertTrue(source_depth_support(1.005, 1, 0.01))

    def test_20_missing_bound_stays_unknown(self):
        self.assertIsNone(conditional_clearance(10, None, 1, 0.1))

    def test_21_conditional_clearance(self):
        self.assertAlmostEqual(conditional_clearance(0.25, 0.07, 1.2, 0.2), 0.06)
        self.assertAlmostEqual(conditional_clearance(0.25, 0.07, 1.2, 0.5), -0.12)

    def test_22_more_uncertainty_cannot_improve_bound(self):
        self.assertLess(conditional_clearance(0.25, 0.12, 1.2, 0.2), conditional_clearance(0.25, 0.07, 1.2, 0.2))

    def test_23_crop_resize_projection_consistent(self):
        c, p, x0, y0, scale = Camera(), (0.3, 0.1, 2), 120, 80, 0.5
        resized = Camera(c.fx * scale, c.fy * scale, (c.cx - x0) * scale, (c.cy - y0) * scale)
        expected = tuple((a - origin) * scale for a, origin in zip(c.project(p), (x0, y0)))
        self.assertEqual(resized.project(p), expected)

    def test_24_nonfinite_and_negative_depth_rejected(self):
        for p in ((0, 0, -1), (0, 0, 0), (float('inf'), 1, 2)):
            with self.assertRaises(ValueError):
                Camera().project(p)
        with self.assertRaises(ValueError):
            Camera(fx=-1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GeometryProof))
    report = {
        'evidence_class': 'authored synthetic mathematics, not model or robot validation',
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'source_view_scale_ambiguity': {'scale_multiplier': 1.3, 'same_projection': True,
                                      'translation_m': 0.3, 'true_depth_m': 2, 'focal_px': 1000,
                                      'new_view_error_px': abs(1000 * 0.3 / 2 - 1000 * 0.3 / 2.6)},
        'parallax': {'near_m': 2, 'far_m': 5, 'translation_m': 0.3, 'relative_displacement_px': 90.0},
        'depth_sensitivity': {'near_m': 1, 'far_m': 5, 'near_to_far_ratio': 25.0},
        'conditional_clearance': {'sampled_m': 0.25, 'error_bound_m': 0.07, 'speed_bound_m_s': 1.2,
                                  'gap_0_2_s_bound_m': conditional_clearance(0.25, 0.07, 1.2, 0.2),
                                  'gap_0_5_s_bound_m': conditional_clearance(0.25, 0.07, 1.2, 0.5),
                                  'physical_qualification': False},
        'model_inference_runs': 0, 'paid_requests': 0, 'hardware_actions': 0,
    }
    text = json.dumps(report, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    print(text, end='')
    return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
