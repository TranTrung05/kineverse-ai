"""Mô hình bàn tay động học thuận (FK) 21 điểm kiểu MediaPipe – dùng cho DEMO MODE và kiểm thử.

Gần thực tế hơn synthetic cũ: các đốt ngón có độ dài thật, ngón cong theo khớp (MCP/PIP/DIP), ngón cái
được đặt bằng tìm kiếm ngẫu nhiên để chạm đúng mục tiêu (đầu ngón trỏ khi chụm, mặt ngón khi nắm).
Có thể xoay bàn tay (roll/yaw/pitch) và thêm nhiễu giống MediaPipe để đo độ nhầm lẫn giữa các cử chỉ.

Đơn vị: hand_size = 1 = khoảng cách cổ tay -> khớp gốc ngón giữa. x phải, y xuống, z âm = gần camera.
Dữ liệu sinh ra là GIẢ LẬP – không phải kết quả đo trên người thật.
"""
from __future__ import annotations

import numpy as np

# (MCP x, y), chiều dài 3 đốt, góc xòe ngang (độ) của ngón trỏ, giữa, nhẫn, út
_FINGERS = [
    ((-0.33, -0.95), (0.42, 0.24, 0.20), -7.0),
    ((0.00, -1.00), (0.47, 0.26, 0.21), 0.0),
    ((0.30, -0.94), (0.44, 0.25, 0.21), 5.0),
    ((0.57, -0.80), (0.35, 0.19, 0.18), 13.0),
]
_THUMB_BASE = np.array([-0.26, -0.14, 0.0])
_THUMB_LEN = (0.34, 0.36, 0.28, 0.25)      # 0->1, 1->2, 2->3, 3->4

# Góc gập (độ) của (MCP, PIP, DIP) cho từng mức ngón: duỗi, thả lỏng, nắm
FLEX_STRAIGHT = (0.0, 0.0, 0.0)
FLEX_RELAXED = (30.0, 40.0, 20.0)
FLEX_FIST = (85.0, 100.0, 65.0)
FLEX_PINCH_INDEX = (38.0, 42.0, 22.0)


def _finger_points(k: int, flex, spread_jitter=0.0):
    (mx, my), seg, spread = _FINGERS[k]
    s = np.radians(spread + spread_jitter)
    pts = [np.array([mx, my, 0.0])]
    cum = 0.0
    for length, f in zip(seg, flex):
        cum += np.radians(f)
        d = np.array([np.sin(s), -np.cos(s) * np.cos(cum), -np.cos(s) * np.sin(cum)])
        pts.append(pts[-1] + length * d)
    return pts            # MCP, PIP, DIP, TIP


def _dir(az, el):
    """az: góc trong mặt phẳng ảnh (0 = lên, dương = sang phải); el: góc nhô về phía camera."""
    return np.array([np.sin(az) * np.cos(el), -np.cos(az) * np.cos(el), -np.sin(el)])


def _thumb_chain(params):
    p = [_THUMB_BASE.copy()]
    for i in range(4):
        az, el = params[2 * i], params[2 * i + 1]
        p.append(p[-1] + _THUMB_LEN[i] * _dir(az, el))
    return p


def _thumb_cost(params, target, avoid):
    ch = _thumb_chain(params)
    c = 12.0 * float(np.linalg.norm(ch[4] - target) ** 2)
    for i in range(3):                       # hạn chế gập quá gắt giữa các đốt
        d_az = abs(params[2 * i + 2] - params[2 * i])
        d_el = abs(params[2 * i + 3] - params[2 * i + 1])
        c += 0.25 * (max(0, d_az - 0.8) ** 2 + max(0, d_el - 0.8) ** 2)
    for q in ch[2:]:                         # không xuyên vào lòng bàn tay (z > 0)
        c += 4.0 * max(0.0, q[2] - 0.02) ** 2
    for q in avoid:                          # không xuyên qua các đốt ngón khác
        for c_pt in ch[2:]:
            c += 0.6 * max(0.0, 0.07 - float(np.linalg.norm(c_pt - q))) ** 2 * 50
    return c


def solve_thumb(target, avoid=(), seed=0, iters=1500):
    rng = np.random.default_rng(seed)
    best = np.array([-1.0, 0.2, -0.9, 0.3, -0.8, 0.3, -0.7, 0.3])
    best_c = _thumb_cost(best, target, avoid)
    step = 0.35
    for i in range(iters):
        cand = best + rng.normal(0, step, 8)
        cand[0::2] = np.clip(cand[0::2], -2.6, 1.0)
        cand[1::2] = np.clip(cand[1::2], -0.6, 1.3)
        c = _thumb_cost(cand, target, avoid)
        if c < best_c:
            best, best_c = cand, c
        if i == 600:
            step = 0.15
        if i == 1100:
            step = 0.06
    return _thumb_chain(best)


THUMB_OPEN = [_THUMB_BASE.copy()]
for _az, _el, _l in [(-0.9, 0.15, 0.34), (-0.95, 0.15, 0.36), (-0.95, 0.1, 0.28), (-0.95, 0.1, 0.25)]:
    THUMB_OPEN.append(THUMB_OPEN[-1] + _l * _dir(_az, _el))


def build_pose(flex, thumb="open", thumb_target=None, seed=0, jitter=0.0, rng=None):
    """Trả mảng (21,3) trong hệ tọa độ bàn tay. flex: 4 bộ (mcp,pip,dip) cho trỏ..út.
    thumb: 'open' | 'target' (dùng thumb_target: 'index_tip' | 'index_mid' | 'middle_mid' | 'index_pip')."""
    rng = rng or np.random.default_rng(seed)
    fingers = [_finger_points(k, tuple(np.array(flex[k]) + rng.normal(0, 4 * jitter, 3)),
                              rng.normal(0, 3 * jitter)) for k in range(4)]
    pts = np.zeros((21, 3))
    for k, f in enumerate(fingers):
        pts[5 + 4 * k: 9 + 4 * k] = np.array(f)
    if thumb == "open":
        ch = THUMB_OPEN
    else:
        tgt = {"index_tip": fingers[0][3], "index_mid": (fingers[0][1] + fingers[0][2]) / 2,
               "middle_mid": (fingers[1][1] + fingers[1][2]) / 2, "index_pip": fingers[0][1],
               "ring_mid": (fingers[2][1] + fingers[2][2]) / 2}[thumb_target]
        tgt = tgt + rng.normal(0, 0.02 * (1 + 3 * jitter), 3)
        avoid = [q for f in fingers for q in f[1:]]
        ch = solve_thumb(tgt, avoid, seed=int(rng.integers(1 << 30)))
    pts[1:5] = np.array(ch[1:5])
    return pts


# --- thư viện tư thế -------------------------------------------------------------------
def pose_variants(label: str, rng):
    """Sinh 1 biến thể ngẫu nhiên của một cử chỉ. label: OPEN_PALM|FIST|POINTING|TWO_FINGERS|PINCH[_OPEN|_RELAXED|_CURLED]|FIST_THUMB_ON_INDEX"""
    j = 1.0
    S, R, F = FLEX_STRAIGHT, FLEX_RELAXED, FLEX_FIST
    if label == "OPEN_PALM":
        return build_pose([S, S, S, S], "open", rng=rng, jitter=j)
    if label == "FIST":
        tgt = rng.choice(["index_mid", "middle_mid", "ring_mid"])
        return build_pose([F, F, F, F], "target", tgt, rng=rng, jitter=j)
    if label == "FIST_THUMB_ON_INDEX":      # nắm đấm, ngón cái ép lên đốt giữa ngón trỏ – dễ nhầm với chụm nhất
        return build_pose([F, F, F, F], "target", "index_mid", rng=rng, jitter=j)
    if label == "FIST_THUMB_ALONGSIDE":
        return build_pose([F, F, F, F], "open", rng=rng, jitter=j)
    if label == "POINTING":
        return build_pose([S, F, F, F], "target", "middle_mid", rng=rng, jitter=j)
    if label == "TWO_FINGERS":
        return build_pose([S, S, F, F], "target", "ring_mid", rng=rng, jitter=j)
    if label.startswith("PINCH"):
        idx = tuple(np.array(FLEX_PINCH_INDEX) + rng.normal(0, 6, 3))
        mode = label.split("_", 1)[1] if "_" in label else rng.choice(["OPEN", "RELAXED", "CURLED"])
        other = {"OPEN": S, "RELAXED": R, "CURLED": F}[mode]
        return build_pose([idx, other, other, other], "target", "index_tip", rng=rng, jitter=j)
    raise ValueError(label)


def transform(pts, rng=None, roll=0.0, yaw=0.0, pitch=0.0, flip_z=False):
    """Xoay quanh trọng tâm bàn tay (độ). yaw: quanh trục y, pitch: quanh trục x, roll: quanh trục z (trong ảnh)."""
    p = pts.copy()
    if flip_z:                      # mu bàn tay hướng camera
        p[:, 2] *= -1
    c = p[[0, 5, 9, 13, 17]].mean(axis=0)
    a, b, g = np.radians([roll, yaw, pitch])
    Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    Ry = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(g), -np.sin(g)], [0, np.sin(g), np.cos(g)]])
    return (p - c) @ (Rz @ Ry @ Rx).T + c


def to_landmarks(pts, cx=0.5, cy=0.6, scale=0.25, aspect=1.0, noise=0.0, rng=None):
    """Đưa về 21 điểm (x, y, z) chuẩn hóa như MediaPipe. noise: độ lệch chuẩn theo đơn vị hand_size."""
    p = pts.copy()
    if noise and rng is not None:
        p[:, :2] += rng.normal(0, noise, (21, 2))
        p[:, 2] += rng.normal(0, noise * 2.5, 21)
    return [(cx + scale * x / aspect, cy + scale * y, scale * z / aspect) for x, y, z in p]


_CACHE: dict = {}


def cached_pose(label: str, seed: int = 0):
    """Tư thế cố định (cache) cho demo/test xác định."""
    key = (label, seed)
    if key not in _CACHE:
        _CACHE[key] = pose_variants(label, np.random.default_rng(seed))
    return _CACHE[key]
