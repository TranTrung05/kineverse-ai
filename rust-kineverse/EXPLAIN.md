Cargo.toml: Cấu hình thư viện cdylib (cho Python nạp qua C-ABI/ctypes hoặc PyO3) và rlib (cho Rust thuần / WebAssembly sau này).

- src/types.rs: Định nghĩa 21 điểm Landmarks 3D, các cử chỉ tĩnh (OPEN_PALM, PINCH, FIST, POINTING, TWO_FINGERS), trạng thái máy (IDLE, ACTIVE, GRABBING).

- src/features.rs: Chuyển đổi chính xác 100% công thức extract_features từ Python (tỉ lệ duỗi ngón, hình dạng vòng chụm ring_shape, ngưỡng hysteresis pinch_on/pinch_off).

- src/one_euro.rs: Bộ lọc OneEuro 3D mượt mà, Zero-Allocation (hoàn toàn không cấp phát bộ nhớ Heap).

- src/engine.rs: Máy trạng thái GestureEngine, phát hiện cử chỉ vuốt động (SWIPE_LEFT, SWIPE_RIGHT, SWIPE_UP, SWIPE_DOWN) và tự động nhả RELEASE khi mất tay.

- src/ffi.rs: Giao tiếp chuẩn C-ABI (extern "C") để Python gọi thẳng hoặc sau này xuất sang WebAssembly .wasm.

- src/main.rs: Trình kiểm thử và đo Benchmark độc lập 1.000.000 lần lặp.

TEST TỐC ĐỘ
============================================================
           BENCHMARK PYTHON GESTURE ENGINE
============================================================
[Python] OPEN_PALM: label=OPEN_PALM, conf=1.000
[Python] PINCH:     label=PINCH, conf=0.965, ratio=0.045

Chạy extract_features trong Python (30,000 lần)...
-> Tổng thời gian Python: 1259.28 ms
-> Thời gian mỗi lần gọi: 41.98 µs (microseconds)
-> Thông lượng: 23,823 khung hình/giây

Chạy OneEuro filter trong Python (30,000 lần)...
-> Tổng thời gian OneEuro: 173.35 ms
-> Thời gian mỗi lần gọi: 5.78 µs (microseconds)