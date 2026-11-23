"""Găng tay cảm biến DIY (ESP32 + 5 flex + MPU6050) qua Serial; có mock mode khi chưa có phần cứng.

Dòng dữ liệu từ firmware (JSON, 1 dòng/mẫu):  {"t":12345,"f":[raw x5],"imu":[ax,ay,az,gx,gy,gz]}
  f: giá trị ADC thô 0..4095 (thumb, index, middle, ring, pinky); imu: gia tốc (g), vận tốc góc (dps).
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from pathlib import Path

from ..events import InputEvent
from ..gesture import GestureEngine
from .base import InputDevice

log = logging.getLogger("glove")
MOCK_OPEN, MOCK_CLOSED = 800.0, 3000.0


def classify_pattern(bent, curls):
    """bent: 5 bool (cái, trỏ, giữa, nhẫn, út; True = gập). Trả (label, confidence)."""
    th, ix, md, rg, pk = bent
    if not (ix or md or rg or pk):
        label = "OPEN_PALM"
    elif ix and md and rg and pk:
        label = "FIST"
    elif th and ix and not (md or rg or pk):
        label = "PINCH"
    elif not ix and md and rg and pk:
        label = "POINTING"
    elif not ix and not md and rg and pk:
        label = "TWO_FINGERS"
    else:
        return "UNKNOWN", 0.0
    conf = min(max(0.0, min(1.0, 0.6 + 0.8 * abs(c - 0.5))) for c in curls)
    return label, conf


class GloveInput(InputDevice):
    name = "glove"

    def __init__(self, cfg: dict, data_dir, mode: str | None = None, port: str | None = None):
        self.cfg = cfg
        self.g = cfg["glove"]
        self.mode = mode or self.g["mode"]
        self.port = port or self.g["port"]
        self.simulated = self.mode == "mock"
        self.engine = GestureEngine(cfg["gesture"])
        self.cal_path = Path(data_dir) / "glove_calibration.json"
        self.lo = [MOCK_OPEN] * 5 if self.simulated else [0.0] * 5
        self.hi = [MOCK_CLOSED] * 5 if self.simulated else [4095.0] * 5
        if not self.simulated and self.cal_path.exists():
            try:
                c = json.loads(self.cal_path.read_text())
                self.lo, self.hi = c["lo"], c["hi"]
            except Exception:  # noqa: BLE001
                log.warning("Không đọc được calibration cũ")
        self._ema = [0.0] * 5
        self._bent = [False] * 5
        self._cal_until, self._cal_samples = 0.0, []
        self._stop = threading.Event()

    # ---- vòng đời ----------------------------------------------------------------
    def start(self, sink):
        self.sink = sink
        threading.Thread(target=self._run, name="glove", daemon=True).start()

    def stop(self):
        self._stop.set()

    def calibrate(self):
        """Người dùng xòe tay rồi nắm chặt chậm trong `calibration_s` giây."""
        self._cal_samples, self._cal_until = [], time.monotonic() + self.g["calibration_s"]

    def _run(self):
        if self.mode == "mock":
            self.sink.set_device("glove", True, "MOCK (giả lập)", simulated=True)
            self._mock_loop()
        else:
            self._serial_loop()

    # ---- đọc dữ liệu -------------------------------------------------------------
    def _serial_loop(self):
        while not self._stop.is_set():
            try:
                import serial
                ser = serial.Serial(self.port, self.g["baud"], timeout=0.5)
            except Exception as e:  # noqa: BLE001
                self.sink.set_device("glove", False, f"không mở được {self.port}: {type(e).__name__}")
                self._stop.wait(2.0)
                continue
            self.sink.set_device("glove", True, f"serial {self.port}", simulated=False)
            last_ok = time.monotonic()
            try:
                while not self._stop.is_set():
                    line = ser.readline()
                    if not line:
                        if time.monotonic() - last_ok > 1.5:
                            self.sink.set_device("glove", False, "mất dữ liệu (timeout)")
                        continue
                    try:
                        d = json.loads(line.decode("utf-8", "ignore"))
                        self.process_sample(d["f"], d.get("imu"), time.perf_counter())
                        last_ok = time.monotonic()
                        self.sink.set_device("glove", True, f"serial {self.port}", simulated=False)
                    except (ValueError, KeyError, TypeError):
                        continue   # bỏ qua dòng hỏng
            except Exception as e:  # noqa: BLE001
                self.sink.set_device("glove", False, f"lỗi serial: {type(e).__name__}")
            finally:
                try:
                    ser.close()
                except Exception:  # noqa: BLE001
                    pass

    def _mock_loop(self):
        """Giả lập găng tay: lặp các tư thế ngón tay + thỉnh thoảng có cú vung cổ tay."""
        seq = [("OPEN_PALM", 1.4), ("POINTING", 1.0), ("TWO_FINGERS", 1.0), ("PINCH", 1.2), ("FIST", 1.0)]
        pat = {"OPEN_PALM": [0, 0, 0, 0, 0], "POINTING": [1, 0, 1, 1, 1], "TWO_FINGERS": [1, 0, 0, 1, 1],
               "PINCH": [1, 1, 0, 0, 0], "FIST": [1, 1, 1, 1, 1]}
        hz, i, sign = 50, 0, 1
        t0 = time.perf_counter()
        while not self._stop.is_set():
            for name, dur in seq:
                n = int(dur * hz)
                for k in range(n):
                    if self._stop.is_set():
                        return
                    raw = [MOCK_OPEN + (MOCK_CLOSED - MOCK_OPEN) * b + math.sin(i * 0.7 + j) * 30
                           for j, b in enumerate(pat[name])]
                    gz = 260.0 * sign if (name == "OPEN_PALM" and 35 <= k < 40) else 0.0
                    self.process_sample(raw, [0, 0, 1, 0, 0, gz], time.perf_counter())
                    i += 1
                    time.sleep(1 / hz)
                if name == "OPEN_PALM":
                    sign = -sign

    # ---- xử lý một mẫu -------------------------------------------------------------
    def process_sample(self, raw, imu, t):
        if len(raw) != 5:
            return []
        now = time.monotonic()
        if self._cal_until:
            self._cal_samples.append(list(raw))
            if now >= self._cal_until:
                self._finish_calibration()
        curls = []
        for i, r in enumerate(raw):
            span = self.hi[i] - self.lo[i]
            c = 0.0 if abs(span) < 1e-6 else (r - self.lo[i]) / span
            c = max(0.0, min(1.0, c))
            a = self.g["ema_alpha"]
            self._ema[i] = a * c + (1 - a) * self._ema[i]            # lọc nhiễu EMA
            if self._ema[i] > self.g["curl_on"]:
                self._bent[i] = True
            elif self._ema[i] < self.g["curl_off"]:
                self._bent[i] = False                                 # hysteresis
            curls.append(self._ema[i])
        label, conf = classify_pattern(self._bent, curls)
        events = self.engine.process_static(label, conf, t)
        if imu and len(imu) == 6 and self.engine.current == "OPEN_PALM" and self.engine.state != "GRABBING":
            events += self._imu_swipe(imu, t)
        for ge in events:
            self.sink.emit(InputEvent(
                source="glove", type="sensor", action=ge.action, confidence=ge.confidence, t_capture=t,
                simulated=self.simulated,
                payload={"finger_curl": [round(c, 3) for c in curls], "gesture": ge.gesture}))
        self._last = {"gesture": self.engine.current, "curls": curls}
        return events

    def _imu_swipe(self, imu, t):
        s = self.g["imu_swipe"]
        idx = {"ax": 0, "ay": 1, "az": 2, "gx": 3, "gy": 4, "gz": 5}
        lr, ud = imu[idx[s["axis_lr"]]], imu[idx[s["axis_ud"]]]
        thr = s["threshold_dps"]
        if abs(lr) >= thr and abs(lr) > 1.5 * abs(ud):
            d = "RIGHT" if (lr > 0) != s["invert_lr"] else "LEFT"
            return self.engine.swipe(d, t)
        if abs(ud) >= thr and abs(ud) > 1.5 * abs(lr):
            d = "UP" if (ud > 0) != s["invert_ud"] else "DOWN"
            return self.engine.swipe(d, t)
        return []

    def _finish_calibration(self):
        samples, self._cal_until = self._cal_samples, 0.0
        if len(samples) < 20:
            self.sink.log_info("Calibration thất bại: quá ít mẫu")
            return
        lo, hi = [], []
        for i in range(5):
            col = [s[i] for s in samples]
            start = sorted(col[:10])[5]                    # tay xòe ở đầu phiên
            far = max(col, key=lambda v: abs(v - start))   # giá trị xa nhất = nắm chặt
            lo.append(start)
            hi.append(far)
        if any(abs(h - l) < 300 for l, h in zip(lo, hi)):
            self.sink.log_info("Calibration thất bại: biên độ cảm biến quá nhỏ, kiểm tra dây/flex")
            return
        self.lo, self.hi = lo, hi
        try:
            self.cal_path.parent.mkdir(parents=True, exist_ok=True)
            self.cal_path.write_text(json.dumps({"lo": lo, "hi": hi}))
        except OSError:
            pass
        self.sink.log_info("Calibration găng tay hoàn tất")
