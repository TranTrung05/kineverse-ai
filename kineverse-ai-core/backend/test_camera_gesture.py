"""Test Camera & Nhận diện Cử chỉ Trực quan (OpenCV Window).

Tệp này độc lập, mở Camera trực tiếp qua OpenCV + MediaPipe và hiển thị:
- Khung xương 21 điểm bàn tay (tự vẽ bằng OpenCV, tương thích mọi bản MediaPipe)
- Cử chỉ nhận diện được (OPEN_PALM, PINCH, FIST, POINTING, TWO_FINGERS)
- Lệnh tương ứng gửi cho Unity (ACTIVATE, GRAB, CANCEL, SELECT, SWITCH_MODE)
- FPS và thời gian xử lý cử chỉ (Latency)
- Tự động ưu tiên gọi Rust Engine nếu đã build DLL, hoặc dùng Python Engine.

Cách chạy:
    python backend/test_camera_gesture.py
Nhấn phím 'q' hoặc 'ESC' trên cửa sổ camera để thoát.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import cv2
from kineverse.config import load_config
from kineverse.gesture import GestureEngine, OneEuro, extract_features
from kineverse.inputs.camera import _Landmarker

# Đường dẫn tìm Rust DLL
RUST_DLL_PATH = backend_dir.parent.parent / "rust-kineverse" / "target" / "release" / "kineverse_core.dll"

# 21 Khớp xương nối theo chuẩn MediaPipe
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),         # Ngón cái
    (0, 5), (5, 6), (6, 7), (7, 8),         # Ngón trỏ
    (5, 9), (9, 10), (10, 11), (11, 12),    # Ngón giữa
    (9, 13), (13, 14), (14, 15), (15, 16),  # Ngón nhẫn
    (13, 17), (17, 18), (18, 19), (19, 20), # Ngón út
    (0, 17)                                 # Cổ tay nối gốc út
]


def load_rust():
    if RUST_DLL_PATH.exists():
        try:
            lib = ctypes.CDLL(str(RUST_DLL_PATH))
            print(f"[RUST] Đã nạp thành công Rust Core DLL từ: {RUST_DLL_PATH}")
            return lib
        except Exception as e:
            print(f"[RUST] Không nạp được DLL: {e}")
    return None


def draw_hand_skeleton(frame, lm, width, height, color=(0, 255, 128)):
    """Vẽ 21 điểm và các đường nối khung xương bàn tay."""
    pts = [(int(p[0] * width), int(p[1] * height)) for p in lm]

    # Vẽ đường nối
    for p1_idx, p2_idx in HAND_CONNECTIONS:
        cv2.line(frame, pts[p1_idx], pts[p2_idx], color, 2)

    # Vẽ các khớp
    for i, pt in enumerate(pts):
        # Đầu các ngón tay vẽ to hơn
        radius = 5 if i in (4, 8, 12, 16, 20) else 3
        pt_color = (0, 217, 255) if i in (4, 8) else (255, 255, 255)
        cv2.circle(frame, pt, radius, pt_color, -1)


def main():
    cfg = load_config()
    rust_lib = load_rust()
    engine_name = "RUST ENGINE (C-ABI)" if rust_lib else "PYTHON GESTURE ENGINE"

    print("=" * 65)
    print(f"   KINEVERSE CAMERA TEST - ĐANG DÙNG: {engine_name}")
    print("   Nhấn 'q' hoặc 'ESC' trên cửa sổ camera để dừng.")
    print("=" * 65)

    cam_idx = cfg["camera"].get("index", 0)
    cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print(f"[LỖI] Không thể mở webcam tại index {cam_idx}. Vui lòng kiểm tra lại camera.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        landmarker = _Landmarker(cfg["camera"], backend_dir.parent)
        print(f"[AI] MediaPipe khởi tạo thành công ở chế độ: {landmarker.mode}")
    except Exception as e:
        print(f"[LỖI] Không thể khởi tạo MediaPipe: {e}")
        cap.release()
        return

    py_engine = GestureEngine(cfg["gesture"])
    one_euro = OneEuro(1.5, 20.0, 2.0)

    prev_time = time.perf_counter()
    fps = 0.0

    GESTURE_COLORS = {
        "OPEN_PALM": (0, 255, 0),     # Xanh lá: ACTIVATE
        "PINCH": (0, 217, 255),       # Cyan: GRAB
        "FIST": (0, 0, 255),          # Đỏ: CANCEL
        "POINTING": (255, 138, 0),    # Cam: SELECT
        "TWO_FINGERS": (255, 0, 255), # Tím: SWITCH_MODE
        "UNKNOWN": (180, 180, 180),   # Xám
    }

    ACTION_MAP = {
        "OPEN_PALM": "ACTIVATE",
        "PINCH": "GRAB",
        "FIST": "CANCEL",
        "POINTING": "SELECT",
        "TWO_FINGERS": "SWITCH_MODE",
        "UNKNOWN": "WAITING...",
        "NO_HAND": "NO HAND DETECTED",
    }

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[CẢNH BÁO] Không nhận được frame từ webcam.")
            break

        # Lật gương để tương tác tự nhiên
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        t_now = time.perf_counter()
        dt = t_now - prev_time
        prev_time = t_now
        fps = 0.9 * fps + 0.1 * (1.0 / max(dt, 1e-6))

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        detected_label = "NO_HAND"
        conf = 0.0
        calc_time_us = 0.0

        # Nhận diện Landmark từ MediaPipe (hỗ trợ cả mp.solutions lẫn tasks API)
        lm, hs, hand = landmarker.detect(rgb, int(t_now * 1000))

        if lm is not None:
            # Đo thời gian riêng của thuật toán nhận diện cử chỉ
            t_calc_0 = time.perf_counter()
            detected_label, conf, info = extract_features(
                lm, cfg["gesture"], aspect=w / h, pinching=py_engine.pinching
            )
            events = py_engine.process_static(detected_label, conf, t_now)
            events += py_engine.process_motion(lm[9][0], lm[9][1], t_now)
            calc_time_us = (time.perf_counter() - t_calc_0) * 1_000_000.0

            # Lọc OneEuro tọa độ điểm chụm
            pinch_pt = ((lm[4][0] + lm[8][0]) / 2, (lm[4][1] + lm[8][1]) / 2, (lm[4][2] + lm[8][2]) / 2)
            smooth_pinch = one_euro(pinch_pt, t_now)

            # Vẽ khung xương bàn tay
            draw_hand_skeleton(frame, lm, w, h)

            # Vẽ điểm con trỏ / điểm chụm nổi bật
            px = int(smooth_pinch[0] * w)
            py = int(smooth_pinch[1] * h)
            is_grabbing = py_engine.grabbing
            circle_color = (0, 255, 255) if is_grabbing else (0, 217, 255)
            cv2.circle(frame, (px, py), 12 if is_grabbing else 7, circle_color, -1)
            cv2.circle(frame, (px, py), 15 if is_grabbing else 9, (255, 255, 255), 1)
        else:
            py_engine.on_hand_lost(t_now)
            one_euro.reset()

        # Giao diện HUD trên Camera
        color = GESTURE_COLORS.get(detected_label, (180, 180, 180))
        unity_action = ACTION_MAP.get(detected_label, "NONE")

        # Khung trạng thái góc trái
        cv2.rectangle(frame, (10, 10), (380, 130), (20, 20, 20), -1)
        cv2.rectangle(frame, (10, 10), (380, 130), color, 2)

        cv2.putText(frame, f"CORE: {engine_name}", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 217, 255), 1)
        cv2.putText(frame, f"GESTURE: {detected_label} ({conf*100:.0f}%)", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        cv2.putText(frame, f"ACTION -> UNITY: {unity_action}", (20, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(frame, f"FPS: {fps:.1f} | Gesture Calc: {calc_time_us:.1f} us", (20, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        # Trạng thái GRABBING đặc biệt
        if py_engine.grabbing:
            cv2.putText(frame, "[GRABBING OBJECT]", (w - 240, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

        cv2.imshow("Kineverse AI - Camera Test", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[XONG] Đã đóng camera.")


if __name__ == "__main__":
    main()
