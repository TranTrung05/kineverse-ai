"""HandPipeline: chụm + kéo tay phải sinh GRAB -> MOVE... -> RELEASE; vật thể theo tay (position tuyệt đối)."""
import unittest

from kineverse.hand_pipeline import HandPipeline
from kineverse.synthetic import PARAMS, make_hand
from tests.helpers import CFG


class Sink:
    def __init__(self):
        self.events = []

    def emit(self, ev):
        self.events.append(ev)

    def note(self, *a):
        pass


def feed(pipe, label, n, t0, cx0=0.5, cx1=None, cy0=0.6, cy1=None, fps=30.0):
    cx1 = cx0 if cx1 is None else cx1
    cy1 = cy0 if cy1 is None else cy1
    for i in range(n):
        f = i / max(1, n - 1)
        lm = make_hand(cx=cx0 + (cx1 - cx0) * f, cy=cy0 + (cy1 - cy0) * f, **PARAMS[label])
        pipe.process(lm, 0.99, "right", t0 + i / fps)
    return t0 + n / fps


class PipelineMoveTests(unittest.TestCase):
    def run_drag(self, x0, x1, y0=0.6, y1=0.6):
        sink = Sink()
        pipe = HandPipeline(CFG["gesture"], sink, simulated=True)
        t = feed(pipe, "OPEN_PALM", 12, 0.0, 0.5)
        t = feed(pipe, "PINCH", 12, t, x0, cy0=y0)
        t = feed(pipe, "PINCH", 30, t, x0, x1, y0, y1)
        t = feed(pipe, "OPEN_PALM", 12, t, x1, cy0=y1)
        return sink.events

    def test_drag_right_emits_grab_move_release(self):
        evs = self.run_drag(0.3, 0.7)
        acts = [e.action for e in evs]
        self.assertEqual(acts.count("GRAB"), 1)
        self.assertEqual(acts.count("RELEASE"), 1)
        self.assertGreaterEqual(acts.count("MOVE"), 8)
        self.assertLess(acts.index("GRAB"), acts.index("MOVE"))
        self.assertGreater(len(acts) - 1 - acts[::-1].index("MOVE"), 0)
        self.assertLess(len(acts) - 1 - acts[::-1].index("MOVE"), acts.index("RELEASE"))   # MOVE kết thúc trước RELEASE
        moves = [e for e in evs if e.action == "MOVE"]
        self.assertGreater(sum(m.payload["dx"] for m in moves), 0)                         # sang phải
        self.assertGreater(moves[-1].payload["position"]["x"], moves[0].payload["position"]["x"] + 0.2)
        lm = make_hand(cx=0.7, **PARAMS["PINCH"])
        end_x = (lm[4][0] + lm[8][0]) / 2                                                   # điểm chụm thực của tay ở cuối
        self.assertAlmostEqual(moves[-1].payload["position"]["x"], end_x, delta=0.05)       # bám theo tay

    def test_drag_up_down_direction(self):
        moves = [e for e in self.run_drag(0.5, 0.5, 0.7, 0.4) if e.action == "MOVE"]
        self.assertLess(sum(m.payload["dy"] for m in moves), 0)                            # y giảm = lên

    def test_no_move_when_hand_still_while_pinching(self):
        moves = [e for e in self.run_drag(0.5, 0.5) if e.action == "MOVE"]
        self.assertEqual(moves, [])

    def test_no_move_without_pinch(self):
        sink = Sink()
        pipe = HandPipeline(CFG["gesture"], sink, simulated=True)
        feed(pipe, "OPEN_PALM", 12, 0.0, 0.5)
        feed(pipe, "OPEN_PALM", 8, 1.0, 0.5, 0.52)        # trôi chậm, không phải swipe
        self.assertFalse([e for e in sink.events if e.action == "MOVE"])

    def test_move_stops_after_tracking_lost(self):
        sink = Sink()
        pipe = HandPipeline(CFG["gesture"], sink, simulated=True)
        t = feed(pipe, "OPEN_PALM", 12, 0.0, 0.5)
        t = feed(pipe, "PINCH", 30, t, 0.3, 0.6)
        for i in range(12):
            pipe.process(None, 0.0, "", t + i / 30)
        acts = [e.action for e in sink.events]
        self.assertEqual(acts.count("RELEASE"), 1)
        self.assertEqual(sink.events[-1].action, "RELEASE")


if __name__ == "__main__":
    unittest.main()
