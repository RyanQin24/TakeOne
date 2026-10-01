"""Pure reporting checks for the camera-only SRT latency measurement."""

import unittest

from takeone.motion.srt_latency import summarize


class SrtLatencyTests(unittest.TestCase):
    def test_summary_keeps_samples_and_reports_observed_tail(self):
        result = summarize([0.1, 0.4, 0.2, 0.3])
        self.assertEqual(result["samples_ms"], [100.0, 400.0, 200.0, 300.0])
        self.assertEqual(result["median_ms"], 250.0)
        self.assertEqual(result["p95_observed_ms"], 400.0)
        self.assertEqual(result["maximum_ms"], 400.0)

    def test_summary_requires_a_real_observation(self):
        with self.assertRaises(ValueError):
            summarize([])


if __name__ == "__main__":
    unittest.main()
