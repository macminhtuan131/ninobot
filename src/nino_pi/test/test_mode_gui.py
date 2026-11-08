"""Offscreen Qt checks with a real demo bridge subprocess; no SSH/ROS/motion."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
import unittest
from PyQt5 import QtWidgets, QtTest
from nino_pi.mode_gui import ModeWindow


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = ModeWindow(demo=True)
        self.window.show()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def until(self, predicate, seconds=2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            QtTest.QTest.qWait(20)
        self.fail("GUI condition timed out; " + self.window.notice.text())

    def act(self, action, predicate):
        self.assertTrue(self.window.buttons[action].isEnabled(), action)
        self.window.buttons[action].click()
        self.until(lambda: not self.window.pending and predicate())

    def test_disconnected_and_old_firmware_locked(self):
        self.assertTrue(all(not b.isEnabled() for b in self.window.buttons.values()))
        self.window.handle({"type": "connected", "message": "old firmware"})
        self.assertTrue(all(not b.isEnabled() for b in self.window.buttons.values()))

    def test_offline_project_dashboard_never_connects_or_promotes_demo(self):
        w = self.window
        panel = w.project_panel
        self.assertIsNone(w.process)
        self.assertEqual(w.tabs.count(), 5)
        self.assertEqual(panel.tables[0][2].rowCount(), 30)
        panel.search.setText("gyro")
        table = panel.tables[1][2]
        self.assertTrue(any(not table.isRowHidden(i) for i in range(table.rowCount())))
        self.assertTrue(any(table.isRowHidden(i) for i in range(table.rowCount())))
        table.selectRow(4)
        self.assertIn("SHA256", panel.detail.toPlainText())
        w.handle({"type": "capture", "active": False, "result": {"status": "captured_not_calibrated",
                   "quality_report": {"level": "Q4", "label": "fake"}}})
        self.assertIn("Q0", panel.current.toPlainText())
        self.assertIn("Q0", w.data_panel.quality.text())
        self.assertIsNone(w.process)
        self.assertTrue(all(not b.isEnabled() for b in w.buttons.values()))

    def test_todo_recipe_selection_does_not_reuse_motion_for_future_tasks(self):
        w=self.window
        table=w.project_panel.tables[3][2]
        table.selectRow(10)  # K01..K04 + T01..T07
        self.assertEqual(w.project_panel.selected_recipe,'diagnostic')
        table.selectRow(18)  # T15
        self.assertEqual(w.project_panel.selected_recipe,'future')
        self.assertIsNone(w.process)

    def test_collection_primary_action_remains_visible_on_small_display(self):
        w=self.window;w.resize(900,740);g=w.guided;scroll=w.guided_scroll
        w.acquisition_tabs.setCurrentIndex(1)
        for page in range(6):
            g.wizard.navigation.setCurrentRow(page);self.app.processEvents()
            primary=g.wizard.primary
            top=primary.mapTo(scroll.viewport(),primary.rect().topLeft())
            self.assertTrue(scroll.viewport().rect().contains(top),page)
            self.assertTrue(scroll.viewport().rect().contains(top+primary.rect().bottomRight()),page)
            self.assertEqual(scroll.verticalScrollBar().maximum(),0,page)
        self.assertFalse(g.runner.active_jobs);self.assertIsNone(w.process)

    def test_demo_full_operator_flow(self):
        w = self.window
        w.toggle_connection()
        self.until(lambda: w.state is not None)
        self.assertEqual(w.state["owner"], 0)
        self.assertFalse(w.buttons["arm"].isEnabled())
        self.act("claim", lambda: w.state["owner"] == w.client)
        self.act("ros", lambda: w.state["source"] == 2)
        self.assertFalse(w.state["armed"])
        self.act("arm", lambda: w.state["armed"] == 1)
        self.act("rc", lambda: w.state["source"] == 1 and not w.state["armed"])
        self.assertFalse(w.buttons["arm"].isEnabled())  # no demo RC receiver
        self.act("ros", lambda: w.state["source"] == 2)
        self.act("stop", lambda: w.state["latched"] == 1)
        self.assertFalse(w.buttons["arm"].isEnabled())
        self.act("clear", lambda: not w.state["latched"] and not w.state["armed"])
        self.act("arm", lambda: w.state["armed"] == 1)
        self.act("disarm", lambda: not w.state["armed"])
        self.act("release", lambda: not w.state["owner"])

    def test_bridge_death_never_leaves_arm_button_active(self):
        w = self.window
        w.toggle_connection()
        self.until(lambda: w.state is not None)
        self.act("claim", lambda: w.state["owner"] == w.client)
        self.act("ros", lambda: w.state["source"] == 2)
        w.process.kill()
        self.until(lambda: w.process is None)
        self.assertIsNone(w.state)
        self.assertTrue(all(not b.isEnabled() for b in w.buttons.values()))

    def test_data_tab_forward_capture_review_flow_in_demo(self):
        w = self.window
        panel = w.data_panel
        self.assertEqual(panel.mode.count(), 5)
        self.assertFalse(panel.record.isEnabled())
        w.toggle_connection()
        self.until(lambda: w.state is not None and panel.supported)
        self.act("claim", lambda: w.state["owner"] == w.client)
        self.act("ros", lambda: w.state["source"] == 2)
        panel.mode.setCurrentIndex(panel.mode.findData("forward"))
        panel.prepare.click()
        self.until(lambda: panel.status.get("prepared"))
        panel.pose.setText("unknown caster; same tile heading")
        panel.floor.setText("same floor and load")
        panel.clear.setChecked(True)
        panel.parameters.setChecked(True)
        self.assertTrue(panel.record.isEnabled())
        panel.record.click()
        self.until(lambda: panel.capture.get("ready"))
        self.until(lambda: panel.run.isEnabled())
        self.assertFalse(w.buttons["arm"].isEnabled())
        panel.run.click()
        self.until(lambda: panel.status.get("phase") == "running")
        self.until(lambda: panel.status.get("phase") == "done", seconds=4)
        self.assertFalse(w.state["armed"])
        self.assertFalse(panel.run.isEnabled())
        panel.stop.click()
        self.until(lambda: not panel.capture.get("active"))
        self.assertEqual(panel.capture["result"]["status"], "DEMO_ONLY_NO_DATA")
        self.assertFalse(panel.record.isEnabled())
        panel.observation.setText("DEMO only")
        panel.save.click()
        self.until(lambda: panel.observation_saved)
        panel.reviewed.setChecked(True)
        self.assertTrue(panel.record.isEnabled())


if __name__ == "__main__":
    unittest.main()
