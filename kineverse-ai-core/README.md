# Kineverse AI Core

AI interaction demo kết hợp camera nhận diện bàn tay, găng tay ESP32 và chuột. Core chuyển thao tác thành lệnh gửi qua WebSocket đến Unity; dashboard có cảnh 3D mock để thử nhanh. Cảnh mock không phải Unity thật.

## Yêu cầu

- Windows 10/11
- Python 3.11 64-bit, có Python Launcher (`py`)
- Internet khi cài dependencies

Camera cần webcam. Chạy với găng tay cần ESP32 và cổng Serial phù hợp.

## Cài đặt và chạy

Mở thư mục dự án trong File Explorer hoặc Terminal:

1. Chạy `setup_windows.bat` để tạo môi trường `.venv` và cài dependencies.
2. Chạy một trong các file:

| File | Chức năng |
|---|---|
| `run_demo.bat` | Demo giả lập, không cần camera hay găng tay |
| `run_camera.bat` | Camera thật cùng Unity Mock; nếu không mở được camera, chương trình chuyển sang demo |
| `run_with_glove.bat` | Găng tay ESP32 cùng Unity Mock; sửa `COM3` trong file nếu cổng Serial khác |
| `run_mock_unity.bat` | Chạy Unity Mock riêng |
| `run_tests.bat` | Chạy bộ kiểm thử |

Dashboard tự mở tại [http://127.0.0.1:8080/index.html](http://127.0.0.1:8080/index.html). Dashboard dùng WebSocket tại cổng `8765`; Unity Mock mặc định dùng cổng `8766`.

Có thể chạy core từ Terminal tại thư mục dự án:

```bat
.venv\Scripts\python.exe backend\run_core.py --with-mock --demo
```

Bỏ `--demo` để dùng camera mặc định. Xem các tùy chọn khác bằng:

```bat
.venv\Scripts\python.exe backend\run_core.py --help
```

## Điều khiển cơ bản

- Phím `1`, `2`, `3`: chọn lần lượt CAMERA, GLOVE, MOUSE.
- Chuột: click chọn; kéo để nắm và di chuyển; `Ctrl` + kéo để xoay; lăn để đổi kích thước; nhấp đúp để xác nhận; chuột phải hoặc `Esc` để hủy.
- Camera: xòe tay để kích hoạt; chụm ngón cái và ngón trỏ để nắm, giữ chụm và di chuyển để kéo; mở tay để thả; nắm tay để hủy.

## Cấu hình và lưu ý

- Chỉnh camera, cử chỉ, nguồn vào, Unity và găng tay trong `config.json`.
- Nếu sử dụng cổng Serial khác, cập nhật `COM3` trong `run_with_glove.bat` hoặc truyền `--glove-port` khi chạy core.
- Với MediaPipe Tasks API, cần có model `models/hand_landmarker.task`.
- Camera và ngưỡng nhận diện cử chỉ cần được kiểm tra, tinh chỉnh trên thiết bị thực tế. `run_demo.bat` dùng dữ liệu giả lập, không đại diện cho kết quả từ camera hoặc găng tay.
- Tài liệu giao thức và kiến trúc nằm trong `docs/`, firmware ESP32 trong `firmware/glove_esp32/`.
