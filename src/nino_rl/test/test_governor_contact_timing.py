"""Missing samples must not masquerade as sustained physical response."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_governor_contact_timing.py"
spec = importlib.util.spec_from_file_location("contact_timing", SCRIPT)
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


class ContactTimingTest(unittest.TestCase):
    def test_confirmation_requires_future_samples(self):
        values = [(0., .4), (.02, .2), (.04, .2), (.06, .2), (.08, .2)]
        self.assertIsNone(timing.first_sustained(values, .3, 0., .06))
        self.assertEqual(timing.first_sustained(values, .3, 0., .08),
                         dict(begin_s=.02, confirmed_s=.08))

    def test_missing_interval_cannot_confirm_sustained_response(self):
        self.assertIsNone(timing.first_sustained([(0., .2), (.02, .2), (.08, .2)], .3, 0., .1))

    def test_brief_contact_dip_is_not_sustained_response(self):
        values = [(0., .2), (.02, .4), (.04, .2), (.06, .2), (.08, .2), (.10, .2)]
        self.assertEqual(timing.first_sustained(values, .3, 0., .1),
                         dict(begin_s=.04, confirmed_s=.10))

    def test_nonfinite_sample_breaks_continuity(self):
        self.assertIsNone(timing.first_sustained(
            [(0., .2), (.02, .2), (.04, float("nan")), (.06, .2)], .3, 0., .1))

    def test_milestone_lookup_uses_neither_future_nor_stale_sample(self):
        self.assertIsNone(timing.sample_before([(.1,.4)], .09))
        self.assertIsNone(timing.sample_before([(.1,.4)], .15))
        self.assertEqual(timing.sample_before([(.1,.4),(.12,.2)], .11)["value"], .4)


if __name__ == "__main__":
    unittest.main()
