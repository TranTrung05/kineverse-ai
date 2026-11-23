"""Landmarks -> cử chỉ -> InputEvent. Dùng chung cho camera thật và DEMO MODE."""
from __future__ import annotations

from .events import InputEvent
from .gesture import GestureEngine, OneEuro, extract_features

REF_W, REF_H = 640.0, 480.0      # khung tham chiếu để quy đổi dx, dy chuẩn hóa -> "pixel" (cùng đơn vị với chuột)


class HandPipeline:
    """Ngoài lệnh rời rạc (GRAB/SELECT/...), khi đang chụm (GRABBING) pipeline phát MOVE liên tục theo điểm chụm.

    MOVE mang `position` TUYỆT ĐỐI (đã lọc One-Euro, 0..1 trong khung camera) và `dx`,`dy` TƯƠNG ĐỐI (pixel quy đổi
    640x480) cộng dồn kể từ MOVE trước, nên lệnh bị bỏ (throttle/ACK lỗi) không làm lệch vật thể nếu phía nhận
    dùng position.
    """

    def __init__(self, gesture_cfg: dict, sink, simulated: bool = False):
        self.cfg, self.sink, self.simulated = gesture_cfg, sink, simulated
        self.engine = GestureEngine(gesture_cfg)
        self._filter = OneEuro(gesture_cfg.get("smooth_min_cutoff", 1.5), gesture_cfg.get("smooth_beta", 20.0),
                                  gesture_cfg.get("smooth_d_cutoff", 2.0))
        self._anchor = None          # điểm lọc ở lần MOVE trước
        self._was_grabbing = False
        self._last_move_t = -1e9
        self.move_interval = gesture_cfg.get("move_interval_s", 0.05)
        self.move_deadzone = gesture_cfg.get("move_deadzone", 0.004)

    def _pinch_point(self, lm):
        return ((lm[4][0] + lm[8][0]) / 2, (lm[4][1] + lm[8][1]) / 2, (lm[4][2] + lm[8][2]) / 2)

    def process(self, lm, hscore: float, hand: str, t_cap: float, aspect: float = 1.0) -> dict:
        label, conf = "NO_HAND", 0.0
        move_ev = None
        if lm is None:
            events, lost = self.engine.on_hand_lost(t_cap)
            self._filter.reset()
            self._anchor = None
            self._was_grabbing = False
            if lost:
                self.sink.note("camera", self.simulated, "tracking_lost")
        else:
            label, conf, _ = extract_features(lm, self.cfg, aspect, self.engine.pinching)
            events = self.engine.process_static(label, conf, t_cap)
            events += self.engine.process_motion(lm[9][0], lm[9][1], t_cap)
            grabbing = self.engine.grabbing
            if grabbing and not self._was_grabbing:
                self._filter.reset()          # điểm chụm nhảy khi tay đổi dáng: bắt đầu lọc lại từ lúc GRAB
            self._was_grabbing = grabbing
            cur = self._filter(self._pinch_point(lm), t_cap)
            if grabbing and label == "PINCH":     # khung đang xác nhận thả (tay đã mở) không được tạo MOVE
                move_ev = self._maybe_move(cur, hand, hscore, t_cap, bool(events))
            else:
                self._anchor = None
        for ge in events:
            payload = {"hand": hand, "gesture": ge.gesture, "hand_score": round(hscore, 3), **ge.info}
            if lm is not None:
                # GRAB/RELEASE: điểm chụm; SELECT (chỉ trỏ): đầu ngón trỏ; còn lại: giữa lòng bàn tay
                x, y, z = (self._pinch_point(lm) if ge.action in ("GRAB", "RELEASE")
                           else lm[8] if ge.action == "SELECT" else lm[9])
                payload["position"] = {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)}
            self.sink.emit(InputEvent(source="camera", type="gesture", action=ge.action,
                                      confidence=ge.confidence, payload=payload, t_capture=t_cap,
                                      simulated=self.simulated))
        if move_ev:
            self.sink.emit(move_ev)
        return {"gesture": self.engine.current if lm is not None else "NO_HAND", "raw": label,
                "confidence": round(conf, 3), "state": self.engine.state,
                "pointer": self._pointer(lm, cur if lm is not None else None)}

    def _pointer(self, lm, cur):
        """Con trỏ hiển thị: điểm chụm (đã lọc) khi đang chụm, ngược lại đầu ngón trỏ."""
        if lm is None:
            return None
        if self.engine.pinching:
            return [round(float(cur[0]), 4), round(float(cur[1]), 4)]
        return [round(lm[8][0], 4), round(lm[8][1], 4)]

    def _maybe_move(self, cur, hand, hscore, t, just_grabbed):
        if self._anchor is None or just_grabbed:
            self._anchor = cur.copy()
            self._last_move_t = t
            return None
        if t - self._last_move_t < self.move_interval:
            return None
        dx, dy = float(cur[0] - self._anchor[0]), float(cur[1] - self._anchor[1])
        if (dx * dx + dy * dy) ** 0.5 < self.move_deadzone:
            return None
        self._anchor = cur.copy()
        self._last_move_t = t
        return InputEvent(source="camera", type="gesture", action="MOVE", confidence=0.95,
                          payload={"hand": hand, "gesture": "PINCH_DRAG", "hand_score": round(hscore, 3),
                                   "dx": round(dx * REF_W, 2), "dy": round(dy * REF_H, 2),
                                   "position": {"x": round(float(cur[0]), 4), "y": round(float(cur[1]), 4),
                                                "z": round(float(cur[2]), 4)}},
                          t_capture=t, simulated=self.simulated)
