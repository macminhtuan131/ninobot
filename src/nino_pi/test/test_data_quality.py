"""Grades must not turn file integrity into body motion or deployment evidence."""
import copy
import unittest
from nino_pi.data_quality import assess_capture, load_catalog


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.result = dict(status="captured_not_calibrated", checked_hashes=5, hash_mismatches=[], collector_exit=0,
                           workflow_status="done", body_motion_verified=True)
        self.manifest = dict(status="captured_not_calibrated", reason="duration_reached", issues=[],
                             bag=dict(errors=[], topics={"/motor_fb": {"count": 100}}))
        self.config = dict(topics=[dict(name="/motor_fb", required=True)])

    def test_hashes_and_workflow_never_promote_body_or_q3(self):
        report = assess_capture(self.result, self.manifest, self.config)
        self.assertEqual(report["level"], "Q2")
        checks = {r["name"]: r["verdict"] for r in report["checks"]}
        self.assertEqual(checks["Thân xe / độ lặp / slip"], "chưa xác nhận")
        self.assertEqual(checks["Clock / gap / coverage theo cửa sổ"], "chưa review")

    def test_missing_metadata_channels_hashes_and_interruption_fail_closed(self):
        for change in ("metadata", "samples", "hash", "exit", "duration", "incomplete"):
            with self.subTest(change=change):
                result, manifest = copy.deepcopy(self.result), copy.deepcopy(self.manifest)
                if change == "metadata": manifest["bag"]["errors"] = ["metadata_not_closed"]
                if change == "samples": manifest["bag"]["topics"]["/motor_fb"]["count"] = 0
                if change == "hash": result["hash_mismatches"] = ["bag/a.db3"]
                if change == "exit": result["collector_exit"] = 1
                if change == "duration": manifest["reason"] = "interrupted_partial_session"
                if change == "incomplete": result["status"] = "incomplete"
                self.assertEqual(assess_capture(result, manifest, self.config)["level"], "Q1")
        self.assertEqual(assess_capture(self.result)["level"], "Q1")

    def test_demo_and_absence_never_count_as_real_data(self):
        self.assertEqual(assess_capture(self.result, self.manifest, self.config, demo=True)["level"], "Q0")
        self.assertEqual(assess_capture(dict(status="DEMO_ONLY_NO_DATA"))["level"], "Q0")
        self.assertEqual(assess_capture()["level"], "Q0")

    def test_quality_computation_does_not_modify_original_evidence(self):
        before = copy.deepcopy((self.result, self.manifest, self.config))
        assess_capture(self.result, self.manifest, self.config)
        self.assertEqual((self.result, self.manifest, self.config), before)

    def test_catalog_preserves_missing_and_conflicting_evidence(self):
        c = load_catalog()
        self.assertEqual(len(c["data"]), 30)
        self.assertGreaterEqual(len(c["tasks"]), 28)
        self.assertEqual(len({t["id"] for t in c["tasks"]}), len(c["tasks"]))
        self.assertTrue(all(s["level"] != "Q4" for s in c["sessions"]))
        v2 = next(s for s in c["sessions"] if s["id"] == "clear_floor_repeatability_v2_20261102T102247471316Z")
        self.assertEqual(v2["level"], "Q2")
        self.assertIn("không tiến", v2["outcome"])
        zero = next(s for s in c["sessions"] if s["id"].startswith("zero_feedback"))
        self.assertEqual(zero["level"], "Q1")
        self.assertTrue(all(s["sources"] for s in c["parameters"] + c["tasks"] + c["sessions"] + c["data"]))

    def test_new_real_review_keeps_corrupt_and_aborted_sessions_and_no_motion_release(self):
        c = load_catalog()
        review = c["real_review_2026_11_09"]
        self.assertFalse(review["motion_ready"])
        self.assertFalse(review["stop_guard_active"])
        self.assertEqual(review["hardware_authority"], 0)
        sessions = [s for s in c["sessions"] if s["id"].startswith("sac80k_20261108_")]
        self.assertEqual(len(sessions), 8)
        self.assertEqual(sum(s["level"] == "Q1" for s in sessions), 2)
        self.assertEqual(sum("ABORTED" in s["outcome"] for s in sessions), 3)
        self.assertTrue(all("không TD3" in s["claim"] for s in sessions))
        measurement = next(d for d in c["data"] if d["id"] == "D14")
        self.assertIn("camera không bắt buộc", measurement["name"])
