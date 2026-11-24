# LƯU Ý:
- Đã viết sẵn unity-bridge/KineverseBridge.cs để nối kineverse-ai với unity
- Nhét file này tại thư mục sau trong unity: ...\NCKH_UTT\Assets\Scripts\Core\KineverseBridge.cs
- Cách hoạt động của KineverseBridge.cs

1. Nối thẳng vào cơ chế tương tác của Lab:
Nhận lệnh GRAB (chụm tay) → Tự động gọi playerInteractor.BeginGrab(Target) để nhấc bảng mạch / linh kiện trong phòng thí nghiệm.
Nhận lệnh RELEASE (mở tay) → Tự động gọi playerInteractor.EndGrab() để thả vật thể xuống bàn.
Nhận lệnh MOVE / SCALE → Điều chỉnh khoảng cách cầm vật thể xa / gần (holdDistance).
Nhận lệnh SELECT → Bật/tắt highlight vật phẩm (HighlightManager.Instance.Toggle).
2. Sẵn sàng cho cả WebGL lẫn Standalone:
Ở chế độ Editor/Desktop: Tự mở Socket nhận dữ liệu theo kineverse-interaction/1.0.
Ở chế độ WebGL: Cung cấp sẵn hàm OnWebCommand(string json) để JavaScript từ trang web truyền thẳng dữ liệu vào Unity với độ trễ 0 ms.

# Integration Contract – AI Core ↔ Unity  (`kineverse-interaction/1.0`)

Giao thức này là **đề xuất**; chưa có API Unity nào được giả định. Unity Mock (`backend/kineverse/mock_unity.py`) cài đặt đúng đặc tả này để thành viên Unity đối chiếu.

## 1. Kết nối
- Unity là **WebSocket server**, AI Core là **client**. Endpoint mặc định `ws://127.0.0.1:8766/interaction` (đổi trong `config.json → unity.url`).
- Văn bản JSON UTF-8, mỗi frame một thông điệp. `timestamp` = epoch giây (số thực). Trường chưa biết phải được bỏ qua (tương thích tiến).
- AI Core tự kết nối lại mỗi `reconnect_s` (2 s). Khi mất kết nối, các lệnh đang chờ báo `NOT_CONNECTED`.

## 2. Thông điệp
| `type`            | Hướng        | Ý nghĩa                                                                                               |
| ----------------- | ------------ | ----------------------------------------------------------------------------------------------------- |
| `connect`         | Core → Unity | bắt tay: `{type, protocol, client, timestamp}`                                                        |
| `connect_ack`     | Unity → Core | `{type, protocol, server, timestamp}`                                                                 |
| `interaction`     | Core → Unity | **lệnh điều khiển** (xem 3)                                                                           |
| `interaction_ack` | Unity → Core | phản hồi bắt buộc cho mỗi `interaction`                                                               |
| `device_status`   | Core → Unity | mỗi 1 s: `{active_source, devices:{camera,glove,mouse:{connected,detail,simulated}}}` (không cần ACK) |
| `system_status`   | Core → Unity | mỗi 1 s: `{fps, proc_ms, e2e_mean_ms, e2e_p95_ms, ...}` (không cần ACK)                               |
| `ping` / `pong`   | hai chiều    | tùy chọn, Unity gửi `ping` thì Core trả `pong`                                                        |

Tương ứng các endpoint logic đã đề xuất: `/connect` = `connect`, `/interaction` = `interaction`, `/device/status` = `device_status`, `/system/status` = `system_status` (tất cả đi qua một WebSocket; chỉ path `/interaction` được chấp nhận).

## 3. Lệnh `interaction`
```json
{"type":"interaction","message_id":"cmd_000012","source":"camera","command":"GRAB",
 "timestamp":1730000000.123,"payload":{"position":[0.5,0.4,0.2],"hand":"right","gesture":"PINCH"}}
```
`source` chỉ để log/thống kê; **Unity không được rẽ nhánh theo source**.

| `command`                      | Khi nào                                                  | `payload` thường gặp                                                                                                                                                                               |
| ------------------------------ | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ACTIVATE`                     | bắt đầu / chọn chế độ                                    | `position`                                                                                                                                                                                         |
| `SELECT`                       | chọn mục tiêu                                            | `position` (0..1 trong khung nhìn của nguồn; camera: đầu ngón trỏ)                                                                                                                                 |
| `GRAB` / `RELEASE`             | nắm / thả                                                | `position` (camera: điểm chụm); RELEASE có thể kèm `reason:"tracking_lost"`                                                                                                                        |
| `MOVE_LEFT/RIGHT/UP/DOWN`      | swipe (rời rạc, 1 bước)                                  | `dist`                                                                                                                                                                                             |
| `MOVE` / `ROTATE`              | liên tục (chuột; **camera: MOVE khi đang chụm**, ~20 Hz) | `dx`, `dy` (pixel quy đổi, cộng dồn từ lệnh trước), `position` **tuyệt đối** 0..1 (camera: điểm chụm đã lọc). Nên đặt vật theo `position` + độ lệch lúc GRAB; `dx,dy` dùng khi không có `position` |
| `SCALE`                        | liên tục (chuột)                                         | `delta` (±0.08 mỗi nấc)                                                                                                                                                                            |
| `SWITCH_MODE`                  | đổi chế độ                                               | –                                                                                                                                                                                                  |
| `CONFIRM` / `CANCEL` / `RESET` | xác nhận / hủy / đặt lại                                 | –                                                                                                                                                                                                  |

Mỗi lệnh luôn là lệnh nghiệp vụ; **không có** logic kéo thả/vật lý ở phía AI Core.

## 4. Phản hồi `interaction_ack`
```json
{"type":"interaction_ack","message_id":"cmd_000012","status":"ok","timestamp":1730000000.140}
{"type":"interaction_ack","message_id":"cmd_000013","status":"error","error_code":"OBJECT_NOT_FOUND","error":"..."}
```
- Phải trả lời **trong < 1 s** (`ack_timeout_s`), nếu không Core ghi `TIMEOUT`.
- `status:"ok"` nên gửi ngay khi lệnh được nhận/xếp hàng (không chờ render xong); nếu muốn đo độ trễ tới lúc áp dụng, thêm `applied_at` (epoch giây) – Core sẽ lưu trong raw.
- `message_id` phải khớp. Lệnh **idempotent** khi có thể (RELEASE/CANCEL/RESET nhận nhiều lần vẫn an toàn).

## 5. Trạng thái hiển thị trên dashboard
`Command sent` → `ACK ✓ (e2e ms)` / `FAILED` / `TIMEOUT` / `NOT_CONNECTED`; panel Unity hiển thị connected, endpoint, last command, last response, nút Reconnect.

## 6. Gợi ý phía Unity (minh họa, CHƯA biên dịch/kiểm thử)
Dùng thư viện WebSocket server cho Unity (ví dụ websocket-sharp). Quan trọng: callback mạng chạy ngoài main thread → đẩy lệnh vào hàng đợi và xử lý trong `Update()`.
```csharp
public class InteractionService : WebSocketBehavior {          // path "/interaction"
  protected override void OnMessage(MessageEventArgs e) {
    var m = JsonUtility.FromJson<Msg>(e.Data);                   // Msg { type, message_id, command, source }
    if (m.type == "connect")     Send("{\"type\":\"connect_ack\",\"protocol\":\"kineverse-interaction/1.0\"}");
    if (m.type == "interaction") { MainThreadQueue.Enqueue(m);   // xử lý ở Update()
      Send("{\"type\":\"interaction_ack\",\"message_id\":\"" + m.message_id + "\",\"status\":\"ok\"}"); }
  }
}
```
Nếu Unity đã có UDP hay giao thức khác, chỉ cần thay `UnityClient` (cùng giao diện `send_command`); phần còn lại không đổi.

## 7. Version
Đổi phá vỡ tương thích → tăng major (`/2.0`). Thêm trường → tăng minor.
