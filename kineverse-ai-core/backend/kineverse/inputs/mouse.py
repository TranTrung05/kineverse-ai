"""Mouse/Keyboard: dashboard gửi sự kiện thô (GRAB, MOVE, SCALE...), lớp này chuẩn hóa thành InputEvent."""
from __future__ import annotations

from ..events import InputEvent
from .base import InputDevice


class MouseInput(InputDevice):
    name = "mouse"

    def start(self, sink):
        self.sink = sink
        sink.set_device("mouse", True, "dashboard", simulated=False)

    def submit(self, action: str, payload: dict):
        """Gọi trong event loop (từ WebSocket dashboard)."""
        self.sink.emit_local(InputEvent(source="mouse", type="pointer", action=str(action), confidence=1.0,
                                        payload=payload if isinstance(payload, dict) else {}))
