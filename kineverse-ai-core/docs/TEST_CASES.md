# Test cases

## A. Tự động (`run_tests.bat` hoặc `python -m unittest discover -s tests -t .` trong `backend/`) – 43 test
| Nhóm | Nội dung |
|---|---|
| test_gesture | phân loại 5 cử chỉ tĩnh; hysteresis pinch; ACTIVATE không lặp; GRAB→RELEASE; SELECT/SWITCH_MODE/CANCEL; confidence thấp → UNKNOWN; cooldown chống nhấp nháy; mất tay khi GRAB → RELEASE(tracking_lost); swipe 4 hướng, chậm/chéo/không phải OPEN_PALM không kích hoạt |
| test_gesture (bổ sung) | confusion chụm/nắm trên bàn tay FK xoay ±30°, nhiễu 0,02: 0 ca chụm→nắm / nắm→chụm; hồi quy "chụm với ngón trỏ cong"; nháy FIST ngắn khi đang chụm không gây CANCEL |
| test_hand_pipeline | chụm→kéo phải/lên: GRAB → MOVE (position bám tay, dx>0 / dy<0) → RELEASE; tay đứng yên khi chụm không sinh MOVE; mất tay → RELEASE cuối cùng |
| test_interaction | định dạng wire; cùng lệnh từ 3 nguồn; nguồn không hoạt động bị loại; invalid; low-confidence; stale; cooldown (RELEASE miễn); throttle MOVE; trùng event_id; đổi sang thiết bị chưa kết nối; failover |
| test_unity_client | ACK, FAILED, TIMEOUT, NOT_CONNECTED (WebSocket giả) |
| test_recorder | P95; tách dữ liệu SIMULATED/REAL; misread/task/retry; xuất file |
| test_glove | 5 mẫu hình ngón tay; chuỗi sự kiện + cờ simulated; swipe IMU; EMA lọc nhiễu |
| test_pipeline_demo | (~11 s) demo → pipeline → Unity (WS giả) → recorder: đủ ACTIVATE/MOVE_RIGHT/GRAB/RELEASE/SELECT/SWITCH_MODE/CANCEL, 1 pinch = 1 GRAB |

Chưa có test tự động cho: MediaPipe với camera thật, serial thật, `websockets` thật, giao diện trình duyệt (chỉ có smoke test thủ công bằng DOM giả).

## B. Thủ công (cần Windows + phần cứng)
| ID | Bước | Kỳ vọng |
|---|---|---|
| MT-01 | `run_demo.bat` | trình duyệt mở, banner DEMO MODE, log có ACK, Unity ✓ |
| MT-02 | `run_camera.bat`, đưa tay vào | landmarks bám tay, gesture đổi theo tư thế, FPS hiển thị |
| MT-03 | Pinch giữ 1 s rồi thả | đúng 1 GRAB và 1 RELEASE |
| MT-04 | Swipe phải nhanh | 1 MOVE_RIGHT; tay quay về chậm không sinh MOVE_LEFT |
| MT-05 | Che camera/rút tay khi đang pinch | RELEASE(tracking_lost), đếm `LOST` |
| MT-06 | Phím 1/2/3 | banner chuyển nguồn; nguồn chưa kết nối bị từ chối |
| MT-07 | Mouse: click, giữ, kéo, Ctrl+kéo, lăn, dbl, chuột phải | SELECT, GRAB/MOVE/RELEASE, ROTATE, SCALE, CONFIRM, CANCEL |
| MT-08 | Chạy `run_mock_unity.bat --drop-rate 0.3` + core không `--with-mock` | có TIMEOUT hiển thị; `--fail-rate 0.3` có FAILED |
| MT-09 | Tắt Unity Mock giữa chừng | UNITY ✕, NOT_CONNECTED; bật lại tự nối lại hoặc bấm RECONNECT |
| MT-10 | Rút webcam khi đang ở CAMERA >3 s | failover sang nguồn khả dụng theo `priority` |
| MT-11 | Găng tay thật: CALIBRATE, nắm/xòe | trạng thái ngón khớp; `data/glove_calibration.json` được tạo |
| MT-12 | EXPORT | `data/session_*/` có events.csv, commands.csv, tasks.csv, summary.json |
| MT-14 | Camera, SHOWCASE: chụm lên 1 vật, giữ chụm và di chuyển tay chậm rồi nhanh | vật bám theo tay, `MOVES` tăng; thả (mở tay) → `DROPS`+1 |
| MT-15 | Camera: chụm 20 lần liên tiếp (ngón còn lại duỗi / thả lỏng / co), mỗi lần giữ 1 s | `CANCEL-GRAB` = 0; nếu >0 ghi lại tư thế và gửi `ring_shape`/`pinch_ratio` để chỉnh ngưỡng |
| MT-16 | Camera, layout OVERLAP và SIZES | tỷ lệ `GRAB-MISS` thấp; vật nhỏ (0,45×) vẫn nắm được |
| MT-17 | Camera, layout TARGETS | đặt đủ 5 vật vào vòng thả; ghi thời gian |
| MT-18 | Camera: SWITCH_MODE (hai ngón) rồi chụm + kéo tay | MODE ROTATE xoay vật, SCALE phóng/thu theo hướng lên/xuống |
| MT-13 | Laptop văn phòng không GPU | FPS ≥ 20 ổn định (ghi lại số thực) |

## C. Quy trình thực nghiệm so sánh Mouse / Camera / Glove
1. Cố định bộ nhiệm vụ, ví dụ: T1 *SELECT→GRAB→MOVE_RIGHT→RELEASE*, T2 *SELECT→GRAB→MOVE_UP→RELEASE→CONFIRM*; cùng ánh sáng, cùng người, mỗi phương thức ≥ 20 lượt (đảo thứ tự để tránh hiệu ứng học).
2. Mỗi lượt: **START TASK** → thao tác → **TASK OK/FAIL**. Thao tác lại dùng **+ RETRY**; lệnh nhận sai dùng **MARK MISREAD** ngay sau lệnh đó.
3. **EXPORT**; lấy số liệu ở nhóm `…|REAL` trong `summary.json`. Nhóm `…|SIMULATED` (demo/mock) **không** được dùng làm kết quả nghiên cứu.
4. `recognition_accuracy_operator_marked` phụ thuộc người đánh dấu; cần người thứ hai ghi nhận độc lập nếu dùng trong báo cáo.
