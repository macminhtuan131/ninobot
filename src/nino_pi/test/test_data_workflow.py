import unittest
from nino_pi.data_workflow import ClearWindow, Workflow
from nino_pi.gui_capture import profile
from nino_pi.data_bridge import DataBridge, DemoIO


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.commands, self.requests, self.events = [], [], []
        self.flow = Workflow(lambda: self.now, lambda v,w: self.commands.append((v,w)),
                             self.requests.append, lambda n,d: self.events.append((n,d)))
        self.ctx = dict(recording_ready=True, remaining_s=50, owned=True, state_fresh=True,
                        source=2, latched=False, feedback=3, prepared=True, final_zero=True,
                        armed=False, permission=False, problems=[])

    def begin(self, mode="forward"):
        self.flow.reset(mode)
        self.flow.start(self.ctx)
        self.assertEqual(self.commands[-1], (0., 0.))
        self.assertEqual(self.requests, ["arm"])
        self.ctx.update(armed=True, permission=True)
        self.flow.tick(self.ctx)

    def test_forward_exact_window_then_zero_disarm_and_no_retry(self):
        self.begin()
        self.now += 1.99
        self.flow.tick(self.ctx)
        self.assertEqual(self.commands[-1], (.05, 0.))
        self.now += .01
        self.flow.tick(self.ctx)
        self.assertEqual(self.commands[-1], (0., 0.))
        self.assertEqual(self.requests[-1], "disarm")
        self.ctx.update(armed=False, permission=False)
        self.flow.tick(self.ctx)
        self.assertEqual(self.flow.phase, "done")
        with self.assertRaises(ValueError):
            self.flow.start(self.ctx)

    def test_zero_never_sends_nonzero(self):
        self.begin("zero")
        for dt in (1., 1., 1., 1.):
            self.now += dt
            self.flow.tick(self.ctx)
        self.assertTrue(all(c == (0., 0.) for c in self.commands))
        self.assertEqual(self.requests, ["arm", "disarm"])

    def test_no_nonzero_until_arm_permission(self):
        self.flow.reset("forward")
        self.flow.start(self.ctx)
        self.ctx.update(armed=True, permission=False)
        self.flow.tick(self.ctx)
        self.assertEqual(self.flow.phase, "arming")
        self.now += 1.6
        self.flow.tick(self.ctx)
        self.assertEqual(self.flow.phase, "aborted")
        self.assertTrue(all(c == (0., 0.) for c in self.commands))

    def test_stop_aborts_immediately_and_never_resumes(self):
        self.begin()
        self.flow.tick(self.ctx)
        self.ctx["problems"] = ["Collision Monitor STOP"]
        self.flow.tick(self.ctx)
        self.assertEqual(self.requests[-1], "stop")
        self.assertEqual(self.commands[-1], (0., 0.))
        count = len(self.commands)
        self.ctx["problems"] = []
        self.flow.tick(self.ctx)
        self.assertEqual(len(self.commands), count)
        self.assertEqual(self.flow.phase, "aborted")

    def test_recorder_or_telemetry_loss_aborts(self):
        for key, value in (("recording_ready", False), ("state_fresh", False), ("owned", False),
                           ("feedback", 1), ("source", 1), ("prepared", False)):
            self.setUp()
            self.begin()
            self.ctx[key] = value
            self.flow.tick(self.ctx)
            self.assertEqual(self.flow.phase, "aborted", key)

    def test_final_zero_and_recording_required_before_start(self):
        for key, value in (("final_zero", False), ("recording_ready", False), ("armed", True), ("remaining_s", 11)):
            self.setUp()
            self.flow.reset("forward")
            self.ctx[key] = value
            with self.assertRaises(ValueError):
                self.flow.start(self.ctx)
            self.assertEqual(self.requests, [])

    def test_manual_hold_expires_and_reverse_remains_bounded(self):
        self.begin("manual")
        self.flow.hold(-.05, 0.)
        self.flow.tick(self.ctx)
        self.assertEqual(self.commands[-1], (-.01, 0.))
        self.now += .21
        self.flow.tick(self.ctx)
        self.assertEqual(self.commands[-1], (0., 0.))
        for v, w in ((float("nan"), 0), (.051, 0), (0, .101), (.05, .1)):
            with self.assertRaises(ValueError):
                self.flow.hold(v, w)

    def test_observe_and_external_never_start_movement(self):
        for mode in ("stationary", "external"):
            self.flow.reset(mode)
            with self.assertRaises(ValueError):
                self.flow.start(self.ctx)
        self.assertEqual(self.requests, [])

    def test_collector_profiles_do_not_invent_required_messages(self):
        stationary = {r["name"] for r in profile("stationary")["topics"] if r["required"]}
        forward = {r["name"] for r in profile("forward")["topics"] if r["required"]}
        self.assertNotIn("/cmd_vel_teleop", stationary)
        self.assertNotIn("/motor_enable", forward)
        self.assertNotIn("/nino/control_request", stationary)
        self.assertIn("/cmd_vel_teleop", forward)
        self.assertIn("/nino/control_state", forward)
        self.assertNotIn("/odom", forward)
        self.assertEqual(profile("forward")["duration_s"], 60)


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.
        self.scene = ClearWindow(lambda: self.now)

    def fill(self, count=0):
        for _ in range(37):
            self.now += .15
            self.scene.scan(count, True)

    def test_unknown_monitor_not_called_clear(self):
        self.fill()
        self.assertIn("Chưa nhận trạng thái Collision Monitor", self.scene.problems())
        self.scene.monitor(0)
        self.assertEqual(self.scene.problems(), [])

    def test_stop_and_obstacle_prevent_restart_for_clear_window(self):
        self.scene.monitor(0)
        self.fill()
        self.scene.scan(3, True)
        self.assertTrue(self.scene.problems())
        self.scene.monitor(1)
        self.scene.monitor(0)
        self.assertTrue(any("STOP" in s for s in self.scene.problems()))
        self.fill()
        self.assertEqual(self.scene.problems(), [])

    def test_stale_scan_and_invalid_tf_fail_closed(self):
        self.scene.monitor(0)
        self.fill()
        self.now += .6
        self.assertTrue(self.scene.problems())
        self.scene.scan(0, False)
        self.assertTrue(self.scene.problems())


class CoordinatorTests(unittest.TestCase):
    def test_capture_start_cannot_reset_active_sequence_budget(self):
        from types import SimpleNamespace
        session = SimpleNamespace(client=42, state={"armed": 0, "owner": 42}, fresh=lambda: True)
        bridge = DataBridge(session, lambda e: None, DemoIO(), demo=True)
        bridge.handle({"action": "capture_start", "mode": "forward", "metadata": {}})
        bridge.workflow.used = True
        with self.assertRaises(ValueError):
            bridge.handle({"action": "capture_start", "mode": "zero", "metadata": {}})
        self.assertTrue(bridge.workflow.used)
        self.assertEqual(bridge.capture.mode, "forward")

    def test_string_confirmation_does_not_arm(self):
        from types import SimpleNamespace
        session = SimpleNamespace(state={})
        bridge = DataBridge(session, lambda e: None, DemoIO(), demo=True)
        with self.assertRaises(ValueError):
            bridge.handle({"action": "workflow_start", "clear_confirmed": "false", "parameters_confirmed": "true"})


if __name__ == "__main__":
    unittest.main()
