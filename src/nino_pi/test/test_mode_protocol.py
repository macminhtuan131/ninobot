import unittest
from nino_pi.mode_protocol import Session, State, VERSION, MAGIC


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.now = 1.0
        self.sent, self.events = [], []
        self.session = Session(42, self.sent.append, self.events.append, lambda: self.now)
        self.values = [VERSION, MAGIC, 0, 0, 0, 0, 0, 1, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 1000]

    def receive(self, owner=42):
        self.values[2] = owner
        self.values[19] += 100
        self.session.receive(self.values)

    def test_bad_capability(self):
        for index, value in ((0, 2), (1, 0), (4, 3), (5, 2), (11, 4), (18, 1)):
            values = self.values[:]
            values[index] = value
            with self.assertRaises(ValueError):
                State.decode(values)

    def test_missing_and_non_uint(self):
        for values in ([], self.values[:-1], self.values + [0], [True] + self.values[1:], [-1] + self.values[1:]):
            with self.assertRaises(ValueError):
                State.decode(values)

    def test_no_request_without_status(self):
        with self.assertRaises(ValueError):
            self.session.request("claim")
        self.assertEqual(self.sent, [])

    def test_no_automatic_claim_or_heartbeat(self):
        self.receive(owner=0)
        self.session.pulse_at = self.now
        self.session.tick()
        self.assertEqual(self.sent, [])

    def test_claim_needs_explicit_ack(self):
        self.receive(owner=0)
        self.session.request("claim")
        q = self.sent[-1]
        self.assertIsNotNone(self.session.pending)
        self.assertEqual(q, [1, 42, 1, 1, 0])
        self.receive()
        self.assertIsNotNone(self.session.pending)
        self.values[14:17] = [42, q[2], 0]
        self.receive()
        self.assertIsNone(self.session.pending)
        self.assertEqual(self.events[-2]["type"], "ack")

    def test_other_owner_and_pending(self):
        self.receive(owner=555)
        with self.assertRaises(ValueError):
            self.session.request("ros")
        self.session.request("claim")
        with self.assertRaises(ValueError):
            self.session.request("claim")
        self.session.request("stop")
        self.assertEqual(self.sent[-1][3], 6)

    def test_heartbeat_only_with_fresh_ui_and_state(self):
        self.receive()
        self.session.pulse_at = self.now
        self.session.tick()
        self.assertEqual(self.sent[-1][3], 2)
        self.now += 0.5
        self.session.tick()
        self.assertEqual(self.sent[-1][3], 6)
        count = len(self.sent)
        self.session.pulse_at = self.now
        self.receive()
        self.session.tick()
        self.assertEqual(len(self.sent), count)
        self.assertTrue(self.session.halted)
        with self.assertRaises(ValueError):
            self.session.request("arm")

    def test_duplicate_status_does_not_renew_freshness(self):
        self.receive()
        self.now += 0.5
        self.session.receive(self.values)
        self.assertFalse(self.session.fresh())

    def test_ack_timeout_stops_without_retry(self):
        self.receive(owner=0)
        self.session.request("claim")
        self.now += 1.1
        self.session.tick()
        self.assertEqual([q[3] for q in self.sent], [1, 6])
        self.assertTrue(self.session.halted)
        self.assertIsNone(self.session.pending)

    def test_close_stops_releases_only_owner(self):
        self.receive()
        self.session.close()
        self.assertEqual([q[3] for q in self.sent], [6, 8])
        self.sent.clear()
        self.receive(owner=555)
        self.session.close()
        self.assertEqual(self.sent, [])

    def test_late_ack_not_for_current_action(self):
        self.receive()
        self.session.request("ros")
        first = self.sent[-1][2]
        self.session.request("stop")
        self.values[14:17] = [42, first, 0]
        self.receive()
        self.assertEqual(self.session.pending[3], "stop")

    def test_firmware_restart_latches_session(self):
        self.receive()
        self.values[19] = 10
        self.session.receive(self.values)
        self.assertTrue(self.session.halted)
        self.assertEqual(self.sent[-1][3], 6)

    def test_tick_wrap_not_restart(self):
        self.values[19] = 0xFFFFFF00
        self.session.receive(self.values)
        self.values[19] = 100
        self.session.receive(self.values)
        self.assertFalse(self.session.halted)

    def test_reject_inconsistent_armed_state(self):
        self.values[5] = 1
        with self.assertRaises(ValueError):
            State.decode(self.values)


if __name__ == "__main__":
    unittest.main()
