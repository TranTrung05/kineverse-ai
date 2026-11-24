# Ghi chú học Rust qua code nhận diện tay (Kineverse)

---

## Bài 1: `struct`, `impl` và `self`

<details>
<summary>✅ Đã nắm — struct khai báo dữ liệu, impl gắn hành vi, self là đối tượng đang gọi</summary>

### 1. Python gộp, Rust tách

Python: dữ liệu và hành vi nằm chung trong một `class`.

```python
class Point3D:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

    def norm(self):
        return (self.x**2 + self.y**2 + self.z**2) ** 0.5
```

Rust: tách thành hai khối.

```rust
// Khối 1: chỉ khai báo DỮ LIỆU
pub struct Point3D {
    pub x: f32,
    pub y: f32,
    pub z: f32,
}

// Khối 2: khai báo HÀNH VI gắn với kiểu đó
impl Point3D {
    pub fn new(x: f32, y: f32, z: f32) -> Self {
        Self { x, y, z }
    }

    pub fn norm(&self) -> f32 {
        (self.x * self.x + self.y * self.y + self.z * self.z).sqrt()
    }
}
```

`impl Point3D { ... }` = "sau đây là các hàm thuộc về kiểu `Point3D`".

### 2. `self` là gì?

`self` là **chính đối tượng đang gọi hàm**.

- Python: `self` chỉ là tên quy ước, đặt tên khác vẫn chạy.
- Rust: `self` là **từ khóa**, phải viết rõ ở tham số đầu tiên.
- `p.norm()` thực chất là cách viết gọn của `Point3D::norm(&p)`.

### 3. `self` và `Self`

|                 | Nghĩa                    | Ví dụ                         |
| --------------- | ------------------------ | ----------------------------- |
| `self` (thường) | **đối tượng** đang gọi   | `self.x`, `self.hist`         |
| `Self` (hoa)    | **tên kiểu** đang `impl` | `-> Self`, `Self { x, y, z }` |

### 4. `new` không phải từ khóa

- Hàm **không có** `self` gọi bằng `::` (associated function, giống `@staticmethod`): `Point3D::new(1.0, 2.0, 3.0)`
- Hàm **có** `self` gọi bằng dấu chấm (method): `p.norm()`
- Rust không có `__init__`. `new` chỉ là tên quy ước.
- `Self { x, y, z }` là viết gọn của `Self { x: x, y: y, z: z }` khi tên biến trùng tên trường.

### 5. Ba dạng `self`

| Cách viết   | Ý nghĩa                                                     |
| ----------- | ----------------------------------------------------------- |
| `&self`     | chỉ **đọc**, không sửa                                      |
| `&mut self` | được **sửa** đối tượng (`mut` = mutable, "có thể thay đổi") |
| `self`      | **lấy hẳn** đối tượng, dùng xong là mất (học sau)           |

Ví dụ trong `GestureEngine`:

```rust
pub fn is_pinching(&self) -> bool {      // chỉ đọc self.current
    self.current == GestureLabel::Pinch
}

pub fn process_static(&mut self, ...) {  // sửa self.state, self.cand_n, ...
    self.lost = 0;
}
```

Khai báo `&self` mà bên trong sửa `self.lost = 0` thì **trình biên dịch báo lỗi ngay**, trước khi chạy.

### 6. Hai chi tiết cú pháp

- Kiểu viết sau tên: `x: f32`, kiểu trả về: `-> f32`.
- Dòng cuối **không có `;`** chính là giá trị trả về. Thêm `;` vào là lỗi kiểu.

### 7. Hai câu đã giải được nhờ `types.rs`

- `label == self.cand` chạy được vì `#[derive(PartialEq)]` tự sinh phép `==`.
- `action as usize` chạy được vì `GestureAction` là enum không chứa dữ liệu, mỗi biến thể có một số (`Grab = 3`), nên ép kiểu lấy ra số đó để làm chỉ số mảng `last_fire[idx]`.

</details>

---

## Bài 2: Ownership và dấu `&`

<details>
<summary>✅ Đã nắm — 1 chủ sở hữu, nhiều người đọc (&), chỉ 1 người sửa (&mut)</summary>

### 1. Ba cách đưa một giá trị cho hàm

| Cách viết | Tên gọi         | Nghĩa                                 |
| --------- | --------------- | ------------------------------------- |
| `v`       | **move**        | giao hẳn giá trị, mình mất quyền dùng |
| `&v`      | **mượn để đọc** | hàm xem được, không sửa được          |
| `&mut v`  | **mượn để sửa** | hàm sửa được giá trị gốc              |

- `&self` = `self: &Self`, `&mut self` = `self: &mut Self` (viết gọn).
- Python che giấu việc hàm có sửa list hay không; Rust bắt chữ ký hàm nói rõ.

```rust
fn add_one(list: &mut Vec<i32>) {
    list.push(1);
}

fn main() {
    let mut v = Vec::new();   // phải có mut mới sửa được
    add_one(&mut v);          // nơi gọi cũng viết &mut
    println!("{:?}", v);      // [1]
}
```

- Biến mặc định **không sửa được**, muốn sửa phải `let mut`.
- Nơi gọi cũng phải viết `&mut v`.

### 2. Move

```rust
let a = vec![1, 2, 3];
let b = a;                  // quyền sở hữu chuyển từ a sang b
println!("{:?}", a);        // LỖI: a đã bị move
```

Quy tắc cốt lõi: **mỗi giá trị có đúng một chủ sở hữu tại một thời điểm**. Chủ ra khỏi phạm vi thì giá trị tự được giải phóng (Rust không cần garbage collector).

### 3. Kiểu `Copy`

Số và các kiểu nhỏ được **sao chép** khi gán, nên dùng được cả hai biến:

```rust
let x: f32 = 1.5;
let y = x;
println!("{} {}", x, y);   // chạy bình thường
```

`Point3D`, `GestureLabel`, `GestureAction` có `#[derive(Copy)]` trong `types.rs` nên không bị move. `Vec` không có `Copy`, nên phải mượn bằng `&`.

### 4. Luật mượn

Tại một thời điểm, với một giá trị, chỉ được chọn **một** trong hai:

- nhiều `&` (nhiều người cùng đọc), hoặc
- đúng một `&mut` (một người sửa).

### 5. Dấu `*`

`&` tạo tham chiếu, `*` đi theo tham chiếu để lấy giá trị bên trong:

```rust
let (t0, x0, y0) = *self.hist.front().unwrap();
```

Làm được vì tuple của các số là kiểu `Copy`.

</details>

---

## Bài 3: `enum` và `match`

<details>
<summary>✅ Đã nắm — enum giới hạn giá trị hợp lệ, match phải liệt kê đủ mọi trường hợp</summary>

### 1. `enum`

```rust
pub enum GestureLabel {
    Unknown = 0,
    OpenPalm = 1,
    Pinch = 2,
    Fist = 3,
    Pointing = 4,
    TwoFingers = 5,
}
```

- Biến kiểu `GestureLabel` **chỉ có thể là một trong 6 giá trị** này. Gọi bằng `::`: `GestureLabel::Pinch`.
- Gõ sai tên biến thể thì không biên dịch được (Python dùng chuỗi thì chỉ lỗi lúc chạy).
- `= 0, = 1...` là số gán cho mỗi biến thể, `action as usize` lấy ra số này. `#[repr(u8)]` lưu số đó bằng 1 byte.

### 2. `match`

```rust
pub fn as_str(&self) -> &'static str {
    match self {
        Self::OpenPalm => "OPEN_PALM",
        Self::Pinch => "PINCH",
        Self::Fist => "FIST",
        Self::Pointing => "POINTING",
        Self::TwoFingers => "TWO_FINGERS",
        Self::Unknown => "UNKNOWN",
    }
}
```

- Mỗi dòng: `mẫu => kết quả,`.
- `match` là **biểu thức** (có giá trị). Không có `;` sau nó nên giá trị đó là giá trị trả về.
- **Phải liệt kê đủ mọi trường hợp**, thiếu thì báo lỗi. Thêm biến thể mới vào enum thì mọi `match` chưa xử lý đều báo lỗi.
- `&'static str` = chuỗi cố định viết sẵn trong code (phần `'static` học sau).

### 3. `|` và `_`

```rust
match action {
    GestureAction::Grab => self.cfg.grab_cooldown_s as f64,
    GestureAction::MoveLeft
    | GestureAction::MoveRight
    | GestureAction::MoveUp
    | GestureAction::MoveDown => self.cfg.swipe_cooldown_s as f64,
    _ => self.cfg.default_cooldown_s as f64,
}
```

- `A | B | C =>` nghĩa là A **hoặc** B **hoặc** C.
- `_` = tất cả trường hợp còn lại (giống `else`), thường đứng cuối.
- `_ => {}` nghĩa là "các trường hợp còn lại không làm gì".

### 4. `#[derive(...)]`

| Từ          | Cho phép                                                 |
| ----------- | -------------------------------------------------------- |
| `Debug`     | in để gỡ lỗi bằng `{:?}`                                 |
| `Clone`     | sao chép bằng `.clone()`                                 |
| `Copy`      | sao chép tự động khi gán                                 |
| `PartialEq` | so sánh `==`, `!=`                                       |
| `Eq`        | so sánh "đầy đủ" (đi kèm `PartialEq`)                    |
| `Default`   | có giá trị mặc định; `#[default]` chọn biến thể mặc định |

</details>

---

## Bài 4: `Option`

<details>
<summary>✅ Đã nắm — Option thay null, if let/while let để lấy giá trị an toàn, unwrap() chỉ dùng khi chắc chắn</summary>

### 1. `Option` thay cho `null`/`None` của Python

```rust
enum Option<T> {
    Some(T),   // có giá trị, giá trị nằm trong ngoặc
    None,      // không có
}
```

- Rust không có `null`. "Có thể có hoặc không" là một `enum` có sẵn.
- `<T>` = kiểu nào cũng được: `Option<i32>`, `Option<RawGestureEvent>`...
- `Some` là biến thể **mang theo dữ liệu**.

### 2. Hàm `fire`

```rust
fn fire(&mut self, ...) -> Option<RawGestureEvent>

return None;              // chưa hết thời gian chờ: không phát sự kiện
Some(RawGestureEvent { /* ... */ })   // dòng cuối, không có ;: sự kiện hợp lệ
```

- `return None;` thoát sớm giữa hàm. Dòng cuối thì dùng quy tắc "không `;`".

### 3. `if let`

```rust
if let Some(ev) = self.fire(label, action, conf, false, t, 0.0) {
    out_events.push(ev);
}
```

- Nếu khớp `Some(ev)`: lấy giá trị đặt tên `ev` và chạy khối. Nếu `None`: bỏ qua cả khối.
- Là `match` rút gọn khi chỉ quan tâm một trường hợp.

### 4. `.unwrap()`

- Lấy giá trị ra khỏi `Some`; nếu là `None` thì **chương trình dừng (panic)**.
- Chỉ dùng khi **đã chứng minh được** là `Some`. Không chắc thì dùng `if let` hoặc `match`.

### 5. `while let`

```rust
while let Some(&(t0, _, _)) = self.hist.front() {
    if (t - t0) > self.cfg.swipe_window_s as f64 {
        self.hist.pop_front();
    } else {
        break;
    }
}
```

Lặp chừng nào còn khớp `Some`: xóa các điểm cũ hơn `swipe_window_s` giây.

### 6. `VecDeque`

- Hàng đợi hai đầu (giống `collections.deque` của Python).
- `push_back(x)`: thêm vào cuối. `pop_front()`: lấy ra ở đầu. `front()`: xem phần tử đầu, trả `Option`.
- `len()`: **số phần tử** trong hàng đợi.
- Mỗi phần tử trong `hist` là một tuple `(t, x, y)` (thứ tự: thời gian, x, y), tức là một mẫu vị trí lòng bàn tay tại một thời điểm.

### Ghi chú câu kiểm tra

`if self.hist.len() < 3 { return; }` kiểm tra hàng đợi có **ít nhất 3 mẫu** (3 phần tử), không phải kiểm tra tuple có đủ x, y, t. Mỗi tuple luôn đủ ba giá trị.

Bỏ dòng này thì `.unwrap()` **vẫn không panic**, vì ngay trước đó có `self.hist.push_back(...)`, và phần tử mới có `t - t0 = 0` nên vòng `while let` không bao giờ xóa nó. Hàng đợi luôn có ít nhất 1 phần tử.

Dòng `len() < 3` có mục đích khác: cần ít nhất 3 mẫu mới đủ để đánh giá một cú vuốt, tránh quyết định dựa trên 1 đến 2 điểm.

</details>

---

## Bài 5: Tuple, Pattern Matching, Kiểu Số và Ép Kiểu `as`

<details>
<summary>⬜ Chưa kiểm tra — tuple (t, x, y), dùng _ bỏ qua phần tử, as để đổi kiểu số, mảng [T; N]</summary>

### 1. Tuple là gì?

Tuple là **nhóm các giá trị có kiểu khác nhau**, đặt trong dấu ngoặc tròn.

```rust
let point = (1.0_f64, 0.5_f32, 0.3_f32);
//           ^^^^^^   ^^^^^^   ^^^^^^
//           t (giây) x        y
```

Trong `engine.rs`, `hist` lưu lịch sử vị trí bàn tay:

```rust
hist: VecDeque<(f64, f32, f32)>
```

Mỗi phần tử là một tuple `(t, x, y)` — thời gian (f64) và toạ độ (f32, f32). Không phải struct, không có tên trường, truy cập bằng chỉ số `.0`, `.1`, `.2`.

```rust
let item = (1.5_f64, 0.3_f32, 0.7_f32);
println!("{}", item.0);  // 1.5 — thời gian
println!("{}", item.1);  // 0.3 — x
```

### 2. Destructuring — "Bóc" tuple ra từng biến

Thay vì dùng `.0`, `.1`, `.2`, bạn có thể đặt tên ngay khi lấy ra:

```rust
let (t0, x0, y0) = *self.hist.front().unwrap();
//   ^^  ^^  ^^
//   đặt tên cho từng phần tử
```

Dòng này trong `process_motion` lấy phần tử đầu tiên của hàng đợi, bóc ra ba biến: `t0` (thời gian), `x0`, `y0` (toạ độ).

### 3. Dấu `_` trong destructuring — bỏ qua

```rust
while let Some(&(t0, _, _)) = self.hist.front() {
//                   ^  ^
//                   bỏ qua x, y — chỉ cần t0
```

`_` = "tôi biết có giá trị ở đây nhưng không cần dùng".

Nếu đặt tên mà không dùng:
- Rust **in warning**: *"unused variable: x0"*
- Code vẫn chạy, nhưng bị "bẩn"
- Dùng `_` hoặc đặt `_x0` để tắt warning đó

### 4. Dấu `&` trong pattern — `&(t0, _, _)` nghĩa là gì?

`.front()` trả về `Option<&(f64, f32, f32)>` — một **tham chiếu** đến tuple, không phải tuple thật.

```
Some(&(t0, _, _))
     ^
     khớp với tham chiếu, đồng thời "đi vào bên trong" lấy giá trị
```

Nếu không có `&`, phải viết dài hơn:

```rust
while let Some(item) = self.hist.front() {
    let (t0, _, _) = *item;  // * để đi theo tham chiếu
    ...
}
```

Dùng `&(t0, _, _)` trong pattern là viết gọn của hai bước trên thành một.

### 5. Các kiểu số trong Rust

Rust **bắt buộc** bạn nói rõ kiểu số:

| Kiểu    | Nghĩa                            | Dùng ở đâu trong dự án         |
| ------- | -------------------------------- | ------------------------------- |
| `f32`   | số thực 32-bit                   | toạ độ x, y; confidence         |
| `f64`   | số thực 64-bit (chính xác hơn)   | timestamp t                     |
| `u32`   | số nguyên dương 32-bit           | `cand_n`, `stable_frames`       |
| `usize` | số nguyên kích thước tuỳ hệ thống | chỉ số mảng                    |

**Tại sao `t` dùng `f64` còn `x`, `y` dùng `f32`?**
Thời gian cần độ chính xác cao (mili-giây) → `f64`. Toạ độ chỉ cần 0.0–1.0 → `f32` đủ, nhẹ hơn.

### 6. Ép kiểu `as`

Rust **không tự đổi** kiểu số. Muốn đổi phải viết rõ bằng `as`:

```rust
let dt = (t - t0) as f32;
//        ^^^^^^^^  ^^^^
//        f64        đổi sang f32
```

```rust
self.cfg.swipe_window_s as f64
//       ^^^^^^^^^^^^^^  ^^^^
//       f32              đổi sang f64 để so sánh với t (f64)
```

Lý do: `t` là `f64`, `swipe_window_s` là `f32`. Rust không so sánh hai kiểu khác nhau — phải đổi một cái trước.

```rust
let idx = action as usize;
//        ^^^^^^  ^^^^^
//        enum     lấy số (0, 1, 2...) để làm chỉ số mảng
```

### 7. Mảng có kích thước cố định `[T; N]`

```rust
last_fire: [f64; MAX_ACTIONS]  // mảng 16 phần tử f64
```

Khác với `Vec` (thay đổi được kích thước), `[T; N]` cố định ngay từ đầu, nhanh hơn, nằm trên stack.

```rust
last_fire: [-1e9; MAX_ACTIONS]
//          ^^^^  ^^^^^^^^^^^
//          giá trị khởi tạo cho TẤT CẢ 16 phần tử
```

`-1e9` = −1,000,000,000.0 — một timestamp "rất xa trong quá khứ" để lần đầu fire luôn vượt được cooldown.

```rust
const MAX_ACTIONS: usize = 16;
// const = không đổi, dùng được ở mọi nơi trong file
```

</details>

---

## Bài 6: `mod`, `pub`, `use` — Cách các file kết nối nhau

<details>
<summary>⬜ Chưa kiểm tra — mod khai báo module, pub cho phép file khác dùng, use để import</summary>

### 1. Vấn đề: code nằm ở nhiều file, làm sao gọi nhau?

Dự án này có 6 file trong `src/`:

```
src/
├── lib.rs        ← cửa vào của thư viện (entry point)
├── types.rs      ← kiểu dữ liệu
├── engine.rs     ← state machine
├── features.rs   ← tính feature từ landmarks
├── ffi.rs        ← giao tiếp với Python/Unity
└── one_euro.rs   ← bộ lọc làm mượt
```

Rust không tự tìm file. Phải **khai báo tường minh** mới dùng được.

### 2. `mod` — đăng ký file với Rust

Trong `lib.rs`:

```rust
pub mod engine;      // "file engine.rs là một module, cho phép bên ngoài dùng"
pub mod features;
pub mod ffi;
pub mod one_euro;
pub mod types;
```

Mỗi dòng `mod engine;` nói với Rust: *"hãy đọc file `engine.rs`, gắn nó vào đây với tên `engine`"*.

Không có dòng này → file `engine.rs` tồn tại trên đĩa nhưng Rust **hoàn toàn bỏ qua**, không biên dịch.

### 3. `pub` — kiểm soát ai được dùng gì

`pub` = public = cho phép code **bên ngoài** module đó dùng.

Không có `pub` = private = chỉ dùng được **trong cùng file**.

```rust
// types.rs
pub struct Point3D { ... }   // ✅ file khác dùng được
pub enum GestureLabel { ... } // ✅

struct InternalHelper { ... } // ❌ chỉ dùng trong types.rs
```

```rust
// engine.rs
pub struct GestureEngine {
    pub cfg: GestureConfig,      // ✅ đọc/ghi được từ bên ngoài
    pub state: EngineState,      // ✅
    cand: GestureLabel,          // ❌ private — chỉ engine.rs tự dùng
    cand_n: u32,                 // ❌ private
}
```

Tại sao `cand` lại private? Vì đó là trạng thái **nội bộ** của state machine — bên ngoài không được phép sửa trực tiếp, chỉ được thao tác qua các hàm `process_static`, `process_motion`.

### 4. `use` — import để dùng không cần viết đường dẫn đầy đủ

Không có `use`, phải viết dài:

```rust
let e = rust_kineverse::engine::GestureEngine::new(...);
```

Có `use`, viết ngắn:

```rust
use rust_kineverse::engine::GestureEngine;

let e = GestureEngine::new(...);  // gọn hơn
```

Trong `engine.rs`:

```rust
use crate::features::clip;
use crate::types::{
    EngineState, GestureAction, GestureConfig, GestureLabel, RawGestureEvent,
};
use std::collections::VecDeque;
```

- `crate` = thư viện hiện tại (tức là `rust-kineverse` này). Giống `self` nhưng ở cấp độ toàn dự án.
- `std::collections::VecDeque` = lấy từ thư viện chuẩn của Rust.
- `{A, B, C}` = import nhiều thứ từ cùng một đường dẫn, viết gọn.

### 5. `pub use` — re-export: cho phép người dùng import từ chỗ tiện hơn

Trong `lib.rs`:

```rust
pub use engine::GestureEngine;
pub use features::extract_features;
pub use one_euro::OneEuro3D;
pub use types::*;
```

Không có `pub use`, người dùng thư viện phải viết:

```rust
use rust_kineverse::engine::GestureEngine;  // phải biết nó nằm trong engine
```

Có `pub use`, đường dẫn ngắn hơn:

```rust
use rust_kineverse::GestureEngine;  // lấy thẳng từ crate root
```

`types::*` = import **tất cả** những gì `pub` trong `types.rs` — `Point3D`, `GestureLabel`, `GestureConfig`... dùng được ở mọi nơi không cần gõ `types::`.

### 6. Luồng đọc code thực tế

Khi Python gọi vào thư viện này, luồng đi như sau:

```
Python / Unity
     │
     ▼
  ffi.rs          ← nhận dữ liệu raw từ bên ngoài
     │  use crate::engine::GestureEngine
     │  use crate::types::*
     ▼
  engine.rs        ← xử lý state machine
     │  use crate::features::clip
     │  use crate::types::*
     ▼
  features.rs      ← tính toán từ 21 landmarks
     │
     ▼
  types.rs         ← kiểu dữ liệu dùng chung, không import gì từ file khác
```

`types.rs` không `use` file nào trong dự án vì nó là tầng thấp nhất — chỉ định nghĩa kiểu, ai cũng dùng nó nhưng nó không dùng ai.

</details>

---

## Bài tiếp theo

Bài 7: `fn`, tham số, kiểu trả về, và `#[inline(always)]` — đọc hiểu chữ ký hàm trong dự án thực tế.
