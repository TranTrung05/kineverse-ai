"""Sinh landmarks bàn tay giả lập: dùng cho DEMO MODE và kiểm thử. Dữ liệu luôn gắn cờ simulated.

Dựa trên mô hình động học thuận trong handmodel.py (đốt ngón có chiều dài thật, ngón cái chạm đúng mục tiêu).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from .handmodel import (FLEX_FIST, FLEX_PINCH_INDEX, FLEX_STRAIGHT, build_pose, to_landmarks)


@lru_cache(maxsize=64)
def _base_pose(ext: tuple, pinch: bool):
    flex = []
    for i, e in enumerate(ext):
        e = float(e)
        flex.append(tuple(np.array(FLEX_FIST) * (1 - e) + np.array(FLEX_STRAIGHT) * e))
    if pinch:
        flex[0] = FLEX_PINCH_INDEX
        return build_pose(flex, "target", "index_tip", seed=7)
    if all(e >= 0.99 for e in ext):
        return build_pose(flex, "open")
    target = "middle_mid" if ext[1] < 0.5 else "ring_mid"
    return build_pose(flex, "target", target, seed=7)


def make_hand(ext=(1, 1, 1, 1), pinch=False, cx=0.5, cy=0.65, scale=0.25, aspect=1.0):
    """ext: độ duỗi 0..1 của (trỏ, giữa, nhẫn, út). Trả về list 21 điểm (x, y, z) chuẩn hóa. (cx, cy) = tâm lòng bàn tay."""
    pts = _base_pose(tuple(round(float(e), 2) for e in ext), bool(pinch))
    c = pts[[0, 5, 9, 13, 17]].mean(axis=0)
    return to_landmarks(pts - c, cx=cx, cy=cy, scale=scale, aspect=aspect)


PARAMS = {
    "OPEN_PALM": dict(ext=(1, 1, 1, 1)),
    "FIST": dict(ext=(0, 0, 0, 0)),
    "POINTING": dict(ext=(1, 0, 0, 0)),
    "TWO_FINGERS": dict(ext=(1, 1, 0, 0)),
    "PINCH": dict(ext=(0.7, 1, 1, 1), pinch=True),
}


def demo_script(fps: float = 30.0):
    """Kịch bản demo lặp: yield (label|None, cx, cy) mỗi khung hình. None = mất tay.
    Có đoạn chụm rồi kéo tay (GRAB -> MOVE... -> RELEASE) để thử di chuyển vật thể."""
    def hold(label, sec, cx=0.5, cy=0.6):
        return [(label, cx, cy)] * int(sec * fps)

    def sweep(label, x0, x1, sec, y0=0.6, y1=None):
        y1 = y0 if y1 is None else y1
        n = max(2, int(sec * fps))
        return [(label, x0 + (x1 - x0) * i / (n - 1), y0 + (y1 - y0) * i / (n - 1)) for i in range(n)]

    # Tọa độ chọn để điểm chụm/đầu ngón trỏ rơi đúng lên vật trong cảnh 3D SHOWCASE (xem Scene3D.toPx):
    # điểm chụm = tâm lòng bàn tay + (-0.135, -0.121); đầu ngón trỏ khi chỉ = tâm + (-0.136, -0.266).
    seq = (hold(None, 0.8) + hold("OPEN_PALM", 1.0, 0.3, 0.6) + sweep("OPEN_PALM", 0.3, 0.7, 0.22)   # swipe phải
           + hold("OPEN_PALM", 0.6, 0.7) + sweep("OPEN_PALM", 0.7, 0.635, 0.6, 0.6, 0.455) + hold("OPEN_PALM", 0.4, 0.635, 0.455)
           + hold("PINCH", 0.5, 0.635, 0.455)                                                      # GRAB một vật
           + sweep("PINCH", 0.635, 0.40, 1.2, 0.455, 0.62) + sweep("PINCH", 0.40, 0.50, 0.8, 0.62, 0.60)   # kéo vật (MOVE)
           + hold("PINCH", 0.3, 0.50, 0.60) + hold("OPEN_PALM", 0.8, 0.49, 0.6)                    # RELEASE
           + hold("POINTING", 1.0, 0.49, 0.6) + hold("TWO_FINGERS", 1.0, 0.49, 0.6) + hold("FIST", 1.0, 0.49, 0.6)
           + hold(None, 0.6) + hold("OPEN_PALM", 0.6, 0.7))
    while True:
        for item in seq:
            yield item
