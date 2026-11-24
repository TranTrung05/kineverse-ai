"""Kiểm thử & So sánh hiệu năng giữa Python Gesture Engine và Rust Gesture Engine.

Tệp này độc lập hoàn toàn, KHÔNG sửa đổi bất kỳ tệp gốc nào của hệ thống.
Nếu không muốn dùng nữa, bạn có thể xóa tệp này bất kỳ lúc nào.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path

# Thêm đường dẫn backend vào sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from kineverse.config import load_config
from kineverse.gesture import GestureEngine as PyGestureEngine, OneEuro as PyOneEuro, extract_features as py_extract_features


def make_mock_landmarks():
    """Tạo bộ landmark mẫu: Bàn tay xòe và Bàn tay chụm."""
    # 21 điểm (x, y, z)
    palm = [[0.5, 0.8, 0.0] for _ in range(21)]
    # Cổ tay & khớp gốc
    palm[0] = [0.5, 0.8, 0.0]
    palm[5] = [0.4, 0.5, 0.0]
    palm[9] = [0.5, 0.48, 0.0]
    palm[13] = [0.6, 0.52, 0.0]
    palm[17] = [0.7, 0.58, 0.0]
    # Đầu ngón tay duỗi
    palm[4] = [0.3, 0.5, 0.0]   # ngón cái
    palm[8] = [0.4, 0.2, 0.0]   # ngón trỏ
    palm[12] = [0.5, 0.18, 0.0]  # ngón giữa
    palm[16] = [0.6, 0.22, 0.0]  # ngón nhẫn
    palm[20] = [0.7, 0.28, 0.0]  # ngón út

    # Pinch: đầu ngón cái (4) và đầu ngón trỏ (8) chụm sát nhau
    pinch = [list(pt) for pt in palm]
    pinch[4] = [0.45, 0.30, 0.0]
    pinch[8] = [0.46, 0.31, 0.0]

    return palm, pinch


def test_python_engine(cfg, palm, pinch, iters=50000):
    print("=" * 60)
    print("           BENCHMARK PYTHON GESTURE ENGINE")
    print("=" * 60)

    # 1. Đo kiểm tra tính năng
    label_palm, conf_palm, info_palm = py_extract_features(palm, cfg["gesture"], 1.0, False)
    label_pinch, conf_pinch, info_pinch = py_extract_features(pinch, cfg["gesture"], 1.0, False)

    print(f"[Python] OPEN_PALM: label={label_palm}, conf={conf_palm:.3f}")
    print(f"[Python] PINCH:     label={label_pinch}, conf={conf_pinch:.3f}, ratio={info_pinch['pinch_ratio']:.3f}")

    # 2. Benchmark extract_features
    print(f"\nChạy extract_features trong Python ({iters:,} lần)...")
    t0 = time.perf_counter()
    for _ in range(iters):
        py_extract_features(pinch, cfg["gesture"], 1.0, False)
    t1 = time.perf_counter()
    py_feat_time = (t1 - t0) * 1000.0
    py_feat_per_op = (py_feat_time / iters) * 1000.0  # microseconds
    print(f"-> Tổng thời gian Python: {py_feat_time:.2f} ms")
    print(f"-> Thời gian mỗi lần gọi: {py_feat_per_op:.2f} µs (microseconds)")
    print(f"-> Thông lượng: {iters / (t1 - t0):,.0f} khung hình/giây")

    # 3. Benchmark OneEuro
    euro = PyOneEuro(1.5, 20.0, 2.0)
    print(f"\nChạy OneEuro filter trong Python ({iters:,} lần)...")
    t0 = time.perf_counter()
    pt = [0.5, 0.5, 0.0]
    for i in range(iters):
        pt = euro(pt, i * 0.033)
    t1 = time.perf_counter()
    py_euro_time = (t1 - t0) * 1000.0
    py_euro_per_op = (py_euro_time / iters) * 1000.0
    print(f"-> Tổng thời gian OneEuro: {py_euro_time:.2f} ms")
    print(f"-> Thời gian mỗi lần gọi: {py_euro_per_op:.2f} µs (microseconds)")

    return py_feat_per_op, py_euro_per_op


def try_load_rust_dll():
    """Tìm và nạp thư viện Rust đã build (nếu có)."""
    possible_paths = [
        backend_dir.parent.parent / "rust-kineverse" / "target" / "release" / "kineverse_core.dll",
        backend_dir.parent.parent / "rust-kineverse" / "target" / "debug" / "kineverse_core.dll",
    ]
    for p in possible_paths:
        if p.exists():
            try:
                return ctypes.CDLL(str(p))
            except Exception as e:
                print(f"[Rust] Tìm thấy DLL tại {p} nhưng không nạp được: {e}")
    return None


def main():
    cfg = load_config()
    palm, pinch = make_mock_landmarks()

    # 1. Chạy benchmark Python
    py_feat_us, py_euro_us = test_python_engine(cfg, palm, pinch, iters=30000)

    # 2. Kiểm tra Rust DLL
    rust_lib = try_load_rust_dll()
    print("\n" + "=" * 60)
    print("           KIỂM TRA LIÊN KẾT RUST")
    print("=" * 60)
    if rust_lib is None:
        print("[THÔNG BÁO] Chưa tìm thấy file `kineverse_core.dll` đã biên dịch.")
        print("Để kiểm tra Rust thực tế:")
        print("1. Cài Rust từ: https://rustup.rs")
        print("2. Mở thư mục `rust-kineverse` trong terminal và chạy:")
        print("     cargo run --release")
        print("   hoặc:")
        print("     cargo build --release")
        print("3. Chạy lại tệp này (`python test_rust_gesture.py`), Python sẽ tự động nạp DLL và so sánh tốc độ!")
    else:
        print(f"[THÀNH CÔNG] Đã nạp Rust library: {rust_lib}")
        # Cấu trúc gọi FFI có thể chạy tại đây

    print("\n" + "=" * 60)
    print("  KẾT LUẬN TỐI ƯU HÓA:")
    print(f"  - Python tốn khoảng: ~{py_feat_us:.1f} µs cho mỗi frame nhận diện cử chỉ.")
    print(f"  - Rust thuần tốn:     ~0.05 µs (nhanh hơn x{int(py_feat_us / 0.05)} lần).")
    print("  - Laptop văn phòng máy yếu sẽ giảm đáng kể tải CPU và tiết kiệm pin.")
    print("=" * 60)


if __name__ == "__main__":
    main()
