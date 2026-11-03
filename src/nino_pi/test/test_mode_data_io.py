import time
from types import SimpleNamespace as NS
import unittest
from nino_pi.mode_data_io import DataIO


class Future:
    def __init__(self, success=True):
        self.success = success

    def done(self):
        return True

    def result(self):
        return NS(success=self.success)


class IOTests(unittest.TestCase):
    def make_io(self, success=True):
        io = DataIO.__new__(DataIO)
        self.calls, self.topics, self.messages, self.events = [], [], [], []
        io.emit = self.events.append
        io.node = NS(
            get_name=lambda: "bridge",
            get_publishers_info_by_topic=lambda topic: [NS(node_name=n) for n in {
                "/cmd_vel": ["collision_monitor"], "/cmd_vel_selected": ["nino_command_gate"],
                "/cmd_vel_smoothed": ["velocity_smoother"], "/cmd_vel_teleop": []}[topic]],
            create_publisher=lambda typ,topic,qos: self.publisher(topic),
            destroy_publisher=lambda pub: None)
        io.Twist = lambda: NS(linear=NS(x=0.), angular=NS(z=0.))
        io.SetBool = NS(Request=lambda **kwargs: NS(**kwargs))
        io.Trigger = NS(Request=lambda: NS())
        io.clients = {}
        for name in ("gate_enable", "gate_mode", "gate_reset"):
            io.clients[name] = NS(service_is_ready=lambda: True,
                call_async=lambda request, name=name: self.call(name, request, success))
        io.pending = {}
        io.params, io.param_at = {}, {}
        io.prepare_queue, io.prepare_future = [], None
        io.prepare_at = 0.
        io.last_query = io.last_pub = time.monotonic()
        io.publisher = None
        io.prepared, io.preparing_activates = False, False
        io.target = (0., 0.)
        return io

    def publisher(self, topic):
        self.topics.append(topic)
        return NS(publish=lambda m: self.messages.append((m.linear.x, m.angular.z)))

    def call(self, name, request, success):
        self.calls.append((name, getattr(request, "data", None)))
        return Future(success)

    def test_prepare_ack_order_and_source_only(self):
        io = self.make_io()
        io.prepare()
        self.assertFalse(io.prepared)
        for _ in range(4):
            io.tick()
        self.assertTrue(io.prepared)
        self.assertEqual(self.calls, [("gate_enable", False), ("gate_mode", False), ("gate_enable", True)])
        self.assertEqual(self.topics, ["/cmd_vel_teleop"])
        self.assertNotIn("/cmd_vel", self.topics)
        self.assertNotIn("/motor_enable", self.topics)
        self.assertTrue(all(m == (0., 0.) for m in self.messages))
        io.command(.05, 0.)
        io.last_pub = 0
        io.tick()
        self.assertEqual(self.messages[-1], (.05, 0.))
        io.disable()
        self.assertEqual(self.messages[-1], (0., 0.))
        self.assertFalse(io.prepared)
        self.assertIsNone(io.publisher)

    def test_denied_ack_does_not_enable_or_send_nonzero(self):
        io = self.make_io(success=False)
        io.prepare()
        io.tick()
        io.tick()
        self.assertFalse(io.prepared)
        self.assertIsNone(io.publisher)
        self.assertTrue(any(e["type"] == "error" for e in self.events))
        self.assertTrue(all(m == (0., 0.) for m in self.messages))

    def test_gate_reset_remains_disabled(self):
        io = self.make_io()
        io.reset_gate()
        for _ in range(3):
            io.tick()
        self.assertFalse(io.prepared)
        self.assertIsNone(io.publisher)
        self.assertEqual(self.calls[-2:], [("gate_enable", False), ("gate_reset", None)])

    def test_other_manual_publisher_blocks_prepare(self):
        io = self.make_io()
        old = io.node.get_publishers_info_by_topic
        io.node.get_publishers_info_by_topic = lambda t: [NS(node_name="keyboard")] if t == "/cmd_vel_teleop" else old(t)
        with self.assertRaises(ValueError):
            io.prepare()
        self.assertEqual(self.topics, [])

    def test_readonly_connect_close_does_not_disable_somebody_elses_gate(self):
        io = self.make_io()
        io.disable()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.topics, [])


if __name__ == "__main__":
    unittest.main()
