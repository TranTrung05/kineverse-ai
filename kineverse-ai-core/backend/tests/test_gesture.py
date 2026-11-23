import unittest

import numpy as np

from kineverse.gesture import GestureEngine, extract_features
from kineverse.handmodel import FLEX_FIST, build_pose, pose_variants, to_landmarks, transform
from kineverse.synthetic import PARAMS, make_hand
from tests.helpers import CFG

G = CFG["gesture"]


def run_frames(engine, label, n, cx=0.5, t0=0.0, dt=1 / 30, conf=None):
    evs = []
    for i in range(n):
        lm = make_hand(cx=cx, **PARAMS[label])
        lab, c, _ = extract_features(lm, G, 1.0, engine.pinching)
        evs += engine.process_static(lab, c if conf is None else conf, t0 + i * dt)
    return evs


class StaticTests(unittest.TestCase):
    def test_all_static_gestures(self):
        for name, p in PARAMS.items():
            lab, conf, _ = extract_features(make_hand(**p), G)
            self.assertEqual(lab, name)
            self.assertGreaterEqual(conf, G["min_confidence"])

    def test_pinch_hysteresis(self):
        # khoảng cách giữa ngưỡng vào và ra: vẫn là PINCH nếu đang pinch, không phải nếu chưa
        lm = make_hand(**PARAMS["PINCH"])
        base = extract_features(lm, G)[2]["pinch_ratio"]
        mid = (G["pinch_on"] + G["pinch_off"]) / 2
        a, b = np.array(lm[4]), np.array(lm[8])
        lm[4] = tuple(b + (a - b) / max(np.linalg.norm(a - b), 1e-9) * (np.linalg.norm(a - b) * mid / base))
        self.assertEqual(extract_features(lm, G, 1.0, pinching=True)[0], "PINCH")
        self.assertNotEqual(extract_features(lm, G, 1.0, pinching=False)[0], "PINCH")


class PinchVsFistTests(unittest.TestCase):
    """Chụm hay bị nhầm với nắm tay: kiểm tra trên bàn tay FK xoay ngẫu nhiên + nhiễu kiểu MediaPipe (giả lập)."""
    CLASSES = {"FIST": "FIST", "FIST_THUMB_ON_INDEX": "FIST", "FIST_THUMB_ALONGSIDE": "FIST",
               "PINCH_OPEN": "PINCH", "PINCH_RELAXED": "PINCH", "PINCH_CURLED": "PINCH", "OPEN_PALM": "OPEN_PALM"}

    def test_confusion(self):
        rng = np.random.default_rng(11)
        wrong, total, pinch_as_fist, fist_as_pinch = 0, 0, 0, 0
        for lab, exp in self.CLASSES.items():
            for _ in range(8):
                pts = transform(pose_variants(lab, rng), roll=rng.uniform(-30, 30), yaw=rng.uniform(-20, 20),
                                pitch=rng.uniform(-20, 20), flip_z=bool(rng.random() < 0.2))
                got = extract_features(to_landmarks(pts, noise=0.02, rng=rng), G)[0]
                total += 1
                wrong += got != exp
                pinch_as_fist += exp == "PINCH" and got == "FIST"
                fist_as_pinch += exp == "FIST" and got == "PINCH"
        self.assertEqual(pinch_as_fist, 0)
        self.assertEqual(fist_as_pinch, 0)
        self.assertLessEqual(wrong / total, 0.05)

    def test_pinch_with_bent_index_is_not_fist(self):
        """Hồi quy lỗi gốc: khi chụm ngón trỏ cong nên 'độ duỗi' ~0; bộ cũ coi là nắm tay."""
        F = FLEX_FIST
        lm = to_landmarks(build_pose([(48, 58, 30), F, F, F], "target", "index_tip", seed=3))   # trỏ cong nhiều
        lab, _, info = extract_features(lm, G)
        self.assertEqual(lab, "PINCH")
        self.assertLess(info["ext"][0], 0.5)

    def test_brief_fist_flicker_while_pinching_does_not_cancel(self):
        e = GestureEngine(G)
        run_frames(e, "OPEN_PALM", 10)
        run_frames(e, "PINCH", 10, t0=1.0)
        evs = run_frames(e, "FIST", G["fist_after_pinch_frames"] - 1, t0=2.0)   # nháy ngắn sang FIST
        evs += run_frames(e, "PINCH", 6, t0=2.5)
        self.assertEqual(evs, [])
        self.assertEqual(e.state, "GRABBING")
        evs = run_frames(e, "FIST", G["fist_after_pinch_frames"] + 2, t0=3.5)      # nắm thật -> RELEASE rồi CANCEL
        self.assertEqual([x.action for x in evs], ["RELEASE", "CANCEL"])


class EngineTests(unittest.TestCase):
    def test_activate_once_then_no_repeat(self):
        e = GestureEngine(G)
        evs = run_frames(e, "OPEN_PALM", 40)
        self.assertEqual([x.action for x in evs], ["ACTIVATE"])
        self.assertEqual(e.state, "ACTIVE")

    def test_grab_release(self):
        e = GestureEngine(G)
        run_frames(e, "OPEN_PALM", 10)
        evs = run_frames(e, "PINCH", 10, t0=1.0)
        self.assertEqual([x.action for x in evs], ["GRAB"])
        self.assertEqual(e.state, "GRABBING")
        evs = run_frames(e, "OPEN_PALM", 10, t0=2.0)
        self.assertEqual([x.action for x in evs][0], "RELEASE")
        self.assertEqual(e.state, "ACTIVE")

    def test_pointing_two_fingers_fist(self):
        e = GestureEngine(G)
        acts = []
        for i, name in enumerate(["POINTING", "TWO_FINGERS", "FIST"]):
            acts += [x.action for x in run_frames(e, name, 10, t0=i * 2.0)]
        self.assertEqual(acts, ["SELECT", "SWITCH_MODE", "CANCEL"])

    def test_low_confidence_gives_unknown_no_event(self):
        e = GestureEngine(G)
        self.assertEqual(run_frames(e, "FIST", 20, conf=0.3), [])
        self.assertEqual(e.current, "UNKNOWN")

    def test_cooldown_blocks_flicker(self):
        e = GestureEngine(G)
        acts = []
        for i in range(6):   # nhấp nháy open <-> fist: 6 pha x 5 khung @60fps = 0.5s < cooldown 0.6s
            acts += [x.action for x in run_frames(e, "OPEN_PALM" if i % 2 == 0 else "FIST", 5,
                                                  t0=i * 5 / 60, dt=1 / 60)]
        self.assertLessEqual(acts.count("ACTIVATE"), 1)
        self.assertLessEqual(acts.count("CANCEL"), 1)
        self.assertGreater(e.suppressed, 0)

    def test_tracking_lost_while_grabbing_releases(self):
        e = GestureEngine(G)
        run_frames(e, "OPEN_PALM", 10)
        run_frames(e, "PINCH", 10, t0=1.0)
        out, lost = [], False
        for i in range(G["lost_hand_frames"]):
            ev, l = e.on_hand_lost(3.0 + i / 30)
            out += ev
            lost = lost or l
        self.assertTrue(lost)
        self.assertEqual([x.action for x in out], ["RELEASE"])
        self.assertEqual(out[0].info.get("reason"), "tracking_lost")
        self.assertEqual(e.state, "NO_HAND")


class SwipeTests(unittest.TestCase):
    def _swipe(self, dx, dy, dur):
        e = GestureEngine(G)
        run_frames(e, "OPEN_PALM", 10)
        n, evs = 8, []
        for i in range(n):
            f = i / (n - 1)
            evs += e.process_motion(0.5 + dx * f, 0.5 + dy * f, 5.0 + dur * f)
        return [x.action for x in evs]

    def test_four_directions(self):
        self.assertEqual(self._swipe(0.3, 0, 0.25), ["MOVE_RIGHT"])
        self.assertEqual(self._swipe(-0.3, 0, 0.25), ["MOVE_LEFT"])
        self.assertEqual(self._swipe(0, -0.3, 0.25), ["MOVE_UP"])
        self.assertEqual(self._swipe(0, 0.3, 0.25), ["MOVE_DOWN"])

    def test_slow_motion_is_not_swipe(self):
        self.assertEqual(self._swipe(0.3, 0, 1.5), [])

    def test_diagonal_rejected(self):
        self.assertEqual(self._swipe(0.25, 0.25, 0.25), [])

    def test_no_swipe_when_not_open_palm(self):
        e = GestureEngine(G)
        run_frames(e, "FIST", 10)
        evs = []
        for i in range(8):
            evs += e.process_motion(0.3 + 0.05 * i, 0.5, i * 0.03)
        self.assertEqual(evs, [])


if __name__ == "__main__":
    unittest.main()
