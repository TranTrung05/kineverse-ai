import tempfile
import unittest

from kineverse.inputs.glove import GloveInput, MOCK_CLOSED, MOCK_OPEN, classify_pattern
from tests.helpers import CFG


class Sink:
    def __init__(self): self.events, self.infos = [], []
    def emit(self, e): self.events.append(e)
    def log_info(self, t): self.infos.append(t)


def raw_for(pattern):
    return [MOCK_OPEN + (MOCK_CLOSED - MOCK_OPEN) * b for b in pattern]


class GloveTests(unittest.TestCase):
    def test_patterns(self):
        cases = {"OPEN_PALM": [0, 0, 0, 0, 0], "FIST": [1, 1, 1, 1, 1], "PINCH": [1, 1, 0, 0, 0],
                 "POINTING": [1, 0, 1, 1, 1], "TWO_FINGERS": [1, 0, 0, 1, 1]}
        for name, p in cases.items():
            lab, conf = classify_pattern([bool(x) for x in p], [float(x) for x in p])
            self.assertEqual(lab, name)
            self.assertGreater(conf, 0.9)
        self.assertEqual(classify_pattern([False, True, False, True, False], [0, 1, 0, 1, 0])[0], "UNKNOWN")

    def _glove(self):
        g = GloveInput(CFG, tempfile.mkdtemp(), mode="mock")
        g.sink = Sink()
        return g

    def feed(self, g, pattern, n, t0, imu=None):
        for i in range(n):
            g.process_sample(raw_for(pattern), imu or [0, 0, 1, 0, 0, 0], t0 + i * 0.02)

    def test_event_sequence_and_simulated_flag(self):
        g = self._glove()
        self.feed(g, [0] * 5, 30, 0.0)
        self.feed(g, [1, 1, 0, 0, 0], 30, 1.0)
        self.feed(g, [0] * 5, 30, 2.0)
        acts = [e.action for e in g.sink.events]
        # mở bàn tay lại sau khi thả (đã qua cooldown 0.6s) => ACTIVATE lần 2 là hợp lệ
        self.assertEqual(acts, ["ACTIVATE", "GRAB", "RELEASE", "ACTIVATE"])
        self.assertTrue(all(e.simulated and e.source == "glove" for e in g.sink.events))
        self.assertEqual(len(g.sink.events[0].payload["finger_curl"]), 5)

    def test_imu_swipe(self):
        g = self._glove()
        self.feed(g, [0] * 5, 30, 0.0)
        self.feed(g, [0] * 5, 1, 1.0, imu=[0, 0, 1, 0, 0, 300])
        self.assertIn("MOVE_RIGHT", [e.action for e in g.sink.events])

    def test_ema_filters_single_spike(self):
        g = self._glove()
        self.feed(g, [0] * 5, 30, 0.0)
        g.process_sample(raw_for([1, 1, 1, 1, 1]), None, 1.0)        # 1 mẫu nhiễu
        self.feed(g, [0] * 5, 5, 1.02)
        self.assertNotIn("CANCEL", [e.action for e in g.sink.events])


if __name__ == "__main__":
    unittest.main()
