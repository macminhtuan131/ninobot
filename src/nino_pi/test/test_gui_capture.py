import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from nino_pi.gui_capture import Capture, save


class CaptureTests(unittest.TestCase):
    def test_reuses_existing_collector_and_waits_for_actual_bag_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            child = SimpleNamespace(pid=12345, returncode=None, poll=lambda: child.returncode)
            events = []
            capture = Capture(events.append, Path(folder))
            with patch("nino_pi.gui_capture.subprocess.Popen", return_value=child) as popen:
                capture.start("forward", {"pose_caster_note": "unknown", "floor_load_note": "same floor/load"})
            argv = popen.call_args.args[0]
            self.assertIn("nino_pi.collect_real_data", argv)
            self.assertFalse(capture.ready)
            capture.poll()
            self.assertFalse(capture.ready)
            bag = capture.directory / "capture/bag"
            bag.mkdir(parents=True)
            dbpath = bag / "test.db3"
            with sqlite3.connect(dbpath) as db:
                db.execute("CREATE TABLE topics(id INTEGER,name TEXT)")
                db.execute("CREATE TABLE messages(id INTEGER,topic_id INTEGER)")
                for i, r in enumerate(capture.config["topics"], 1):
                    db.execute("INSERT INTO topics VALUES (?,?)", (i, r["name"]))
                    if r["required"]:
                        db.execute("INSERT INTO messages VALUES (?,?)", (i, i))
            capture.last_check = 0
            capture.poll()
            self.assertTrue(capture.ready)
            with patch("nino_pi.gui_capture.os.killpg") as kill:
                capture.stop()
                capture.stop()
                self.assertEqual(kill.call_count, 1)
            capture.last_check = 0
            capture.poll()
            self.assertFalse(capture.ready)
            raw = capture.directory / "capture"
            save(raw / "manifest.json", {"status": "captured_not_calibrated", "issues": []})
            save(raw / "sha256.json", {"bag/test.db3": hashlib.sha256(dbpath.read_bytes()).hexdigest()})
            child.returncode = 0
            capture.last_check = 0
            capture.poll()
            self.assertFalse(capture.active())
            self.assertEqual(capture.result["status"], "captured_not_calibrated")
            self.assertFalse(capture.result["body_motion_verified"])
            self.assertEqual(capture.result["quality_report"]["level"], "Q1")  # fixture manifest has no closure/window evidence
            report = json.loads((capture.directory / "gui_quality_report.json").read_text())
            self.assertEqual(report, capture.result["quality_report"])
            raw_before = dbpath.read_bytes()
            capture.observation("Xe không tiến")
            self.assertEqual(raw_before, dbpath.read_bytes())
            sidecar = json.loads((capture.directory / "sidecar_sha256.json").read_text())
            self.assertEqual(sidecar["events.jsonl"], hashlib.sha256((capture.directory / "events.jsonl").read_bytes()).hexdigest())
            self.assertEqual(sidecar["gui_quality_report.json"], hashlib.sha256((capture.directory / "gui_quality_report.json").read_bytes()).hexdigest())

    def test_hash_failure_preserved_as_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            child = SimpleNamespace(pid=1, returncode=None, poll=lambda: child.returncode)
            capture = Capture(lambda e: None, Path(folder))
            with patch("nino_pi.gui_capture.subprocess.Popen", return_value=child):
                capture.start("stationary", {"pose_caster_note": "unknown", "floor_load_note": "unknown"})
            raw = capture.directory / "capture"
            raw.mkdir()
            save(raw / "manifest.json", {"status": "captured_not_calibrated", "issues": []})
            save(raw / "sha256.json", {"missing.bin": "0"*64})
            child.returncode = 0
            capture.poll()
            self.assertEqual(capture.result["status"], "incomplete")
            self.assertEqual(capture.result["hash_mismatches"], ["missing.bin"])

    def test_metadata_required_unknown_allowed(self):
        capture = Capture(lambda e: None)
        with self.assertRaises(ValueError):
            capture.start("forward", {})


if __name__ == "__main__":
    unittest.main()
