import time
import unittest

from kineverse.events import InputEvent
from kineverse.interaction import InteractionLayer
from tests.helpers import CFG


class FakeClock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


def ev(source="mouse", action="GRAB", conf=1.0, **kw):
    return InputEvent(source=source, type="pointer", action=action, confidence=conf, **kw)


class LayerTests(unittest.TestCase):
    def setUp(self):
        self.clk = FakeClock()
        self.L = InteractionLayer(CFG, clock=self.clk)
        for s in ("camera", "glove", "mouse"):
            self.L.set_device(s, True)
        self.L.set_active("mouse")

    def test_accept_and_wire_format(self):
        d = self.L.handle(ev(payload={"position": {"x": .1, "y": .2, "z": .3}}))
        self.assertTrue(d.accepted)
        w = d.command.to_wire()
        self.assertEqual(w["command"], "GRAB")
        self.assertEqual(w["payload"]["position"], [.1, .2, .3])
        for k in ("type", "message_id", "source", "timestamp", "payload"):
            self.assertIn(k, w)

    def test_same_command_from_every_source(self):
        cmds = []
        for s in ("camera", "glove", "mouse"):
            self.L.set_active(s); self.clk.t += 5
            cmds.append(self.L.handle(ev(source=s, action="SELECT")).command.to_wire()["command"])
        self.assertEqual(cmds, ["SELECT"] * 3)

    def test_inactive_source_rejected(self):
        self.assertEqual(self.L.handle(ev(source="camera")).reason, "inactive_source")

    def test_invalid(self):
        self.assertEqual(self.L.handle(ev(action="FLY")).reason, "invalid_action")
        self.assertEqual(self.L.handle(ev(conf=1.5)).reason, "invalid_confidence")
        self.assertEqual(self.L.handle(ev(source="kinect")).reason, "invalid_source")

    def test_low_confidence_and_stale(self):
        self.assertEqual(self.L.handle(ev(conf=0.2)).reason, "low_confidence")
        self.assertEqual(self.L.handle(ev(t_capture=time.perf_counter() - 5)).reason, "stale")

    def test_cooldown_and_safety_actions(self):
        self.assertTrue(self.L.handle(ev(action="SELECT")).accepted)
        self.assertEqual(self.L.handle(ev(action="SELECT")).reason, "cooldown")
        self.assertTrue(self.L.handle(ev(action="RELEASE")).accepted)
        self.assertTrue(self.L.handle(ev(action="RELEASE")).accepted)   # an toàn: không cooldown
        self.clk.t += 1
        self.assertTrue(self.L.handle(ev(action="SELECT")).accepted)

    def test_continuous_throttle(self):
        self.assertTrue(self.L.handle(ev(action="MOVE")).accepted)
        self.assertEqual(self.L.handle(ev(action="MOVE")).reason, "throttled")
        self.clk.t += 0.1
        self.assertTrue(self.L.handle(ev(action="MOVE")).accepted)

    def test_duplicate_event_id(self):
        e = ev(action="SELECT")
        self.assertTrue(self.L.handle(e).accepted)
        self.clk.t += 1
        self.assertEqual(self.L.handle(e).reason, "duplicate")

    def test_switch_to_disconnected_device_fails(self):
        self.L.set_device("glove", False)
        self.assertEqual(self.L.set_active("glove"), (False, "device_not_connected"))
        self.assertEqual(self.L.active, "mouse")

    def test_failover_after_timeout(self):
        self.L.set_active("camera")
        self.L.set_device("camera", False, "mất camera")
        self.assertIsNone(self.L.check_failover())          # chưa quá timeout
        self.clk.t += CFG["interaction"]["source_timeout_s"] + 0.1
        self.assertEqual(self.L.check_failover(), ("camera", "glove"))
        self.assertEqual(self.L.active, "glove")


if __name__ == "__main__":
    unittest.main()
