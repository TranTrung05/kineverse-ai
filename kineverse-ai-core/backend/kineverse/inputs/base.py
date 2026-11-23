"""Giao diện chung cho mọi thiết bị đầu vào. Thêm thiết bị mới = viết lớp kế thừa InputDevice."""
from __future__ import annotations


class InputDevice:
    name = "base"

    def start(self, sink) -> None:
        """Bắt đầu chạy. `sink` (CoreApp) cung cấp:
        emit(InputEvent) | set_device(source, connected, detail, simulated) | note(source, simulated, name) |
        publish_frame(dict). Mọi hàm của sink an toàn khi gọi từ thread khác."""
        raise NotImplementedError

    def stop(self) -> None:
        pass
