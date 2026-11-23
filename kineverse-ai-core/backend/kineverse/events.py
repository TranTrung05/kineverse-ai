"""Định dạng dữ liệu chuẩn: InputEvent (từ thiết bị) và Command (gửi Unity)."""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

SOURCES = ("camera", "glove", "mouse")
ACTIONS = (
    "ACTIVATE", "GRAB", "RELEASE", "SELECT",
    "MOVE_LEFT", "MOVE_RIGHT", "MOVE_UP", "MOVE_DOWN",
    "MOVE", "ROTATE", "SCALE",
    "SWITCH_MODE", "CONFIRM", "CANCEL", "RESET",
)
CONTINUOUS_ACTIONS = ("MOVE", "ROTATE", "SCALE")   # lệnh liên tục: chỉ throttle
NO_COOLDOWN_ACTIONS = ("RELEASE", "CANCEL", "RESET")  # lệnh an toàn: không bị chặn cooldown

_counter = itertools.count(1)


def next_id(prefix: str) -> str:
    return f"{prefix}_{next(_counter):06d}"


@dataclass
class InputEvent:
    source: str
    type: str                      # gesture | sensor | pointer
    action: str
    confidence: float
    payload: dict = field(default_factory=dict)
    t_capture: float = field(default_factory=time.perf_counter)  # mốc đo độ trễ (perf_counter)
    timestamp: float = field(default_factory=time.time)          # epoch giây (float)
    simulated: bool = False
    event_id: str = field(default_factory=lambda: next_id("evt"))

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id, "timestamp": self.timestamp, "source": self.source,
            "type": self.type, "action": self.action, "confidence": round(self.confidence, 3),
            "payload": self.payload, "simulated": self.simulated,
        }


@dataclass
class Command:
    source: str
    command: str
    payload: dict
    t_capture: float
    simulated: bool = False
    event_id: str = ""
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: next_id("cmd"))

    def to_wire(self) -> dict:
        """Thông điệp gửi Unity (xem docs/INTEGRATION_CONTRACT.md)."""
        return {
            "type": "interaction", "message_id": self.message_id, "source": self.source,
            "command": self.command, "timestamp": self.timestamp, "payload": self.payload,
        }


def position_to_list(pos):
    if isinstance(pos, dict):
        return [pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)]
    return pos
