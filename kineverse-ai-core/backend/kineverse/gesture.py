"""Nhận diện cử chỉ: bộ phân loại tĩnh (landmarks) + máy trạng thái (GestureEngine).

Chỉ phụ thuộc numpy -> kiểm thử được mà không cần camera/MediaPipe.
Chỉ số landmark MediaPipe: 0 cổ tay; 1-4 ngón cái; 5-8 trỏ; 9-12 giữa; 13-16 nhẫn; 17-20 út.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

STATIC_TO_ACTION = {
    "OPEN_PALM": "ACTIVATE", "PINCH": "GRAB", "FIST": "CANCEL",
    "POINTING": "SELECT", "TWO_FINGERS": "SWITCH_MODE",
}
SWIPE_TO_ACTION = {"LEFT": "MOVE_LEFT", "RIGHT": "MOVE_RIGHT", "UP": "MOVE_UP", "DOWN": "MOVE_DOWN"}
TIPS = (8, 12, 16, 20)
MCPS = (5, 9, 13, 17)


def _clip(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def extract_features(lm, cfg: dict, aspect: float = 1.0, pinching: bool = False):
    """Phân loại cử chỉ tĩnh. lm: 21 điểm (x, y, z) chuẩn hóa.

    Trả về (label, confidence, info). label ∈ OPEN_PALM|PINCH|FIST|POINTING|TWO_FINGERS|UNKNOWN.

    PINCH và FIST dễ nhầm nhau vì cả hai đều có đầu ngón cái gần đầu ngón trỏ và ngón trỏ cong. Khác biệt hình học:
    - Chụm: hai đầu ngón tạo thành vòng tròn NHÔ RA XA lòng bàn tay -> điểm chạm (trung điểm 4-8) xa tâm lòng bàn
      tay và đầu ngón trỏ xa khớp gốc của nó.
    - Nắm: đầu ngón trỏ gập vào lòng bàn tay (gần khớp gốc), ngón cái đè lên mặt ngón nên điểm chạm sát lòng bàn tay.
    Vì vậy KHÔNG dùng độ duỗi của ngón trỏ để phân biệt (khi chụm thật ngón trỏ cong nên bị tính là "không duỗi").
    """
    p = np.asarray(lm, dtype=float).copy()
    p[:, 0] *= aspect          # đưa về hệ tọa độ đẳng hướng
    p[:, 2] *= aspect
    d = lambda a, b: float(np.linalg.norm(p[a] - p[b]))
    hand_size = max((d(0, 5) + d(0, 9) + d(0, 13)) / 3.0, 1e-6)

    # Điểm "duỗi" mỗi ngón (trỏ, giữa, nhẫn, út): tỷ lệ khoảng cách đầu ngón / khớp gốc tới cổ tay
    ext = []
    for tip, mcp in zip(TIPS, MCPS):
        r = d(tip, 0) / max(d(mcp, 0), 1e-6)
        ext.append(_clip((r - 1.25) / 0.45))

    pinch_ratio = d(4, 8) / hand_size
    center = p[[0, 5, 9, 13, 17]].mean(axis=0)
    reach = float(np.linalg.norm((p[4] + p[8]) / 2 - center)) / hand_size    # điểm chạm cách lòng bàn tay
    idx_out = d(8, 5) / hand_size                                            # đầu trỏ cách khớp gốc của nó
    shape = 0.5 * _clip((idx_out - cfg.get("idx_out_lo", 0.45)) / cfg.get("idx_out_span", 0.22)) \
        + 0.5 * _clip((reach - cfg.get("reach_lo", 0.68)) / cfg.get("reach_span", 0.18))
    info = {"ext": [round(e, 2) for e in ext], "pinch_ratio": round(pinch_ratio, 3),
            "ring_shape": round(shape, 2)}

    thr = cfg["pinch_off"] if pinching else cfg["pinch_on"]
    shape_min = cfg.get("pinch_shape_hold", 0.25) if pinching else cfg.get("pinch_shape_min", 0.5)
    if pinch_ratio < thr and shape >= shape_min:
        conf = 0.65 + 0.2 * _clip(1 - pinch_ratio / cfg["pinch_on"]) + 0.15 * shape
        return "PINCH", min(conf, 1.0), info

    up = [e > 0.5 for e in ext]
    margin = lambda want: min((e if w else 1 - e) for e, w in zip(ext, want))
    if all(up):
        return "OPEN_PALM", margin([1, 1, 1, 1]), info
    if not any(up):
        return "FIST", margin([0, 0, 0, 0]), info
    if up == [True, False, False, False]:
        return "POINTING", margin([1, 0, 0, 0]), info
    if up == [True, True, False, False]:
        return "TWO_FINGERS", margin([1, 1, 0, 0]), info
    return "UNKNOWN", 0.0, info


class OneEuro:
    """Bộ lọc One-Euro: mượt khi tay đứng yên, ít trễ khi tay di chuyển nhanh."""

    def __init__(self, min_cutoff=1.5, beta=20.0, d_cutoff=2.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self):
        self._x = self._dx = self._t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * np.pi * cutoff)
        return 1.0 / (1.0 + tau / max(dt, 1e-4))

    def __call__(self, x, t):
        x = np.asarray(x, dtype=float)
        if self._x is None:
            self._x, self._dx, self._t = x, np.zeros_like(x), t
            return x
        dt = max(t - self._t, 1e-4)
        a_d = self._alpha(self.d_cutoff, dt)
        dx = (x - self._x) / dt
        self._dx = a_d * dx + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * float(np.linalg.norm(self._dx))
        a = self._alpha(cutoff, dt)
        self._x = a * x + (1 - a) * self._x
        self._t = t
        return self._x


@dataclass
class GestureEvent:
    gesture: str
    action: str
    confidence: float
    kind: str                   # static | dynamic
    t: float
    info: dict = field(default_factory=dict)


class GestureEngine:
    """Máy trạng thái: NO_HAND -> IDLE -> ACTIVE <-> GRABBING.

    - Cử chỉ tĩnh phải ổn định `stable_frames` khung hình liên tiếp.
    - Chỉ phát lệnh khi *chuyển* cử chỉ (edge-triggered), cộng cooldown theo lệnh.
    - Rời PINCH (kể cả mất tay) luôn phát RELEASE để Unity không bị kẹt trạng thái nắm.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.state = "NO_HAND"
        self.current = "UNKNOWN"
        self._cand, self._cand_n = "UNKNOWN", 0
        self._active = False
        self._lost = 0
        self._last_fire: dict = {}
        self._hist: deque = deque()
        self.suppressed = 0
        self.grab_fired = False      # đã phát GRAB cho lần chụm hiện tại -> mới được phát MOVE

    @property
    def pinching(self) -> bool:
        return self.current == "PINCH"

    @property
    def grabbing(self) -> bool:
        return self.current == "PINCH" and self.grab_fired

    def _frames_needed(self, label: str) -> int:
        """Vào cử chỉ mới: stable_frames. Rời PINCH khó hơn (chống nháy khi đang kéo); rời PINCH sang FIST còn khó
        hơn vì FIST = CANCEL, nhầm với chụm là lỗi nặng nhất."""
        n = self.cfg["stable_frames"]
        if self.current == "PINCH" and label != "PINCH":
            n = self.cfg.get("fist_after_pinch_frames", 8) if label == "FIST" else self.cfg.get("release_frames", 5)
        return max(n, self.cfg["stable_frames"])

    def _cooldown(self, action: str) -> float:
        cd = self.cfg["cooldown_s"]
        return cd.get(action, cd["default"])

    def _fire(self, gesture, action, conf, kind, t, info=None):
        if action != "RELEASE":
            last = self._last_fire.get(action)
            if last is not None and (t - last) < self._cooldown(action):
                self.suppressed += 1
                return None
        self._last_fire[action] = t
        return GestureEvent(gesture, action, conf, kind, t, info or {})

    def process_static(self, label: str, conf: float, t: float):
        if self.state == "NO_HAND":
            self.state = "ACTIVE" if self._active else "IDLE"
        self._lost = 0
        if conf < self.cfg["min_confidence"]:
            label = "UNKNOWN"
        if label == self._cand:
            self._cand_n += 1
        else:
            self._cand, self._cand_n = label, 1
        events = []
        if self._cand_n >= self._frames_needed(label) and label != self.current:
            prev, self.current = self.current, label
            if prev == "PINCH":
                self.grab_fired = False
                ev = self._fire("RELEASE_PINCH", "RELEASE", conf, "static", t)
                if ev:
                    events.append(ev)
            action = STATIC_TO_ACTION.get(label)
            if action:
                ev = self._fire(label, action, conf, "static", t)
                if ev:
                    events.append(ev)
                    if action == "GRAB":
                        self.grab_fired = True
                    if action == "ACTIVATE":
                        self._active = True
                    elif action == "CANCEL":
                        self._active = False
            self.state = "GRABBING" if self.current == "PINCH" else ("ACTIVE" if self._active else "IDLE")
        if self.current != "OPEN_PALM":
            self._hist.clear()
        return events

    def process_motion(self, x: float, y: float, t: float):
        """Phát hiện swipe (chỉ khi đang xòe bàn tay, không nắm)."""
        if self.current != "OPEN_PALM" or self.state == "GRABBING":
            self._hist.clear()
            return []
        c = self.cfg
        self._hist.append((t, x, y))
        while self._hist and t - self._hist[0][0] > c["swipe_window_s"]:
            self._hist.popleft()
        if len(self._hist) < 3:
            return []
        t0, x0, y0 = self._hist[0]
        dx, dy, dt = x - x0, y - y0, t - t0
        dist = float(np.hypot(dx, dy))
        if dt < 0.08 or dist < c["swipe_min_dist"] or dist / dt < c["swipe_min_speed"]:
            return []
        ax, ay = abs(dx), abs(dy)
        if max(ax, ay) < c["swipe_axis_ratio"] * min(ax, ay):
            return []  # đường chéo, không rõ hướng
        direction = ("RIGHT" if dx > 0 else "LEFT") if ax > ay else ("DOWN" if dy > 0 else "UP")
        return self.swipe(direction, t, dist)

    def swipe(self, direction: str, t: float, dist: float = 0.0):
        conf = _clip(0.7 + 0.3 * min(1.0, dist / (2 * self.cfg["swipe_min_dist"]))) if dist else 0.85
        ev = self._fire("SWIPE_" + direction, SWIPE_TO_ACTION[direction], conf, "dynamic", t, {"dist": round(dist, 3)})
        self._hist.clear()
        return [ev] if ev else []

    def on_hand_lost(self, t: float):
        """Gọi mỗi khung hình không thấy tay. Trả (events, tracking_lost_xảy_ra)."""
        if self.state == "NO_HAND":
            return [], False
        self._lost += 1
        if self._lost < self.cfg["lost_hand_frames"]:
            return [], False
        events = []
        if self.current == "PINCH":
            events.append(GestureEvent("TRACKING_LOST", "RELEASE", 1.0, "static", t, {"reason": "tracking_lost"}))
        self.grab_fired = False
        self.state, self.current = "NO_HAND", "UNKNOWN"
        self._cand, self._cand_n = "UNKNOWN", 0
        self._hist.clear()
        return events, True
