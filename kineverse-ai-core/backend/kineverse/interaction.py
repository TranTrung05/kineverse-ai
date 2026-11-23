"""Unified Interaction Layer: nhận InputEvent từ mọi nguồn -> kiểm tra, lọc, giải quyết xung đột -> Command."""
from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import Optional

from .events import (ACTIONS, CONTINUOUS_ACTIONS, NO_COOLDOWN_ACTIONS, SOURCES, Command, InputEvent,
                     position_to_list)


@dataclass
class Decision:
    accepted: bool
    reason: str
    event: InputEvent
    command: Optional[Command] = None


class InteractionLayer:
    def __init__(self, cfg: dict, clock=time.monotonic, perf=time.perf_counter):
        self.cfg = cfg["interaction"]
        self.clock, self.perf = clock, perf
        self.active = self.cfg["default_source"]
        self.devices = {s: {"connected": False, "last_seen": None, "simulated": False, "detail": "", "since": clock()}
                        for s in SOURCES}
        self._last_fire: dict = {}
        self._seen = deque(maxlen=1024)
        self.stats = Counter()

    # ---- thiết bị / nguồn điều khiển -------------------------------------------------
    def set_device(self, source: str, connected: bool, detail: str = "", simulated: Optional[bool] = None):
        d = self.devices[source]
        if d["connected"] != connected:
            d["since"] = self.clock()
        d["connected"], d["detail"] = connected, detail
        if simulated is not None:
            d["simulated"] = simulated

    def set_active(self, source: str):
        """Đổi nguồn điều khiển. Trả (ok, reason)."""
        if source not in SOURCES:
            return False, "unknown_source"
        if not self.devices[source]["connected"]:
            return False, "device_not_connected"
        if source != self.active:
            self.active = source
            self._last_fire.clear()
        return True, "ok"

    def check_failover(self):
        """Nếu nguồn đang dùng mất kết nối quá `source_timeout_s` -> chuyển sang nguồn khả dụng theo priority."""
        if not self.cfg.get("failover", True):
            return None
        d = self.devices[self.active]
        if d["connected"] or (self.clock() - d["since"]) < self.cfg["source_timeout_s"]:
            return None
        for s in self.cfg["priority"]:
            if s != self.active and self.devices[s]["connected"]:
                old, self.active = self.active, s
                self._last_fire.clear()
                self.stats["failover"] += 1
                return old, s
        return None

    # ---- xử lý sự kiện ----------------------------------------------------------------
    @staticmethod
    def validate(ev: InputEvent) -> Optional[str]:
        if ev.source not in SOURCES:
            return "invalid_source"
        if ev.action not in ACTIONS:
            return "invalid_action"
        try:
            if not (0.0 <= float(ev.confidence) <= 1.0):
                return "invalid_confidence"
        except (TypeError, ValueError):
            return "invalid_confidence"
        if not isinstance(ev.payload, dict):
            return "invalid_payload"
        return None

    def _reject(self, ev, reason) -> Decision:
        self.stats["rejected_" + reason] += 1
        return Decision(False, reason, ev)

    def handle(self, ev: InputEvent) -> Decision:
        err = self.validate(ev)
        if err:
            return self._reject(ev, err)
        now = self.clock()
        dev = self.devices[ev.source]
        dev["last_seen"], dev["simulated"] = now, ev.simulated
        if ev.event_id in self._seen:
            return self._reject(ev, "duplicate")
        self._seen.append(ev.event_id)
        if ev.source != self.active:
            return self._reject(ev, "inactive_source")
        if self.perf() - ev.t_capture > self.cfg["event_ttl_s"]:
            return self._reject(ev, "stale")
        if ev.confidence < self.cfg["min_confidence"]:
            return self._reject(ev, "low_confidence")
        last = self._last_fire.get(ev.action)
        if ev.action in CONTINUOUS_ACTIONS:
            if last is not None and now - last < self.cfg["continuous_interval_s"]:
                return self._reject(ev, "throttled")
        elif ev.action not in NO_COOLDOWN_ACTIONS:
            if last is not None and now - last < self.cfg["cooldown_s"]:
                return self._reject(ev, "cooldown")
        self._last_fire[ev.action] = now
        payload = dict(ev.payload)
        if "position" in payload:
            payload["position"] = position_to_list(payload["position"])
        cmd = Command(source=ev.source, command=ev.action, payload=payload, t_capture=ev.t_capture,
                      simulated=ev.simulated, event_id=ev.event_id, confidence=ev.confidence)
        self.stats["accepted"] += 1
        return Decision(True, "ok", ev, cmd)
