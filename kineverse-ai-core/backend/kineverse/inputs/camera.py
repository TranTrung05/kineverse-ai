"""Camera AI: OpenCV + MediaPipe Hands. Nếu không mở được camera/thiếu MediaPipe -> DEMO MODE (dữ liệu giả lập)."""
from __future__ import annotations

import base64
import logging
import threading
import time

from ..hand_pipeline import HandPipeline
from ..synthetic import PARAMS, demo_script, make_hand
from .base import InputDevice

log = logging.getLogger("camera")


class _Landmarker:
    """Bọc MediaPipe: ưu tiên mp.solutions.hands, dự phòng Tasks API (cần file .task)."""

    def __init__(self, cfg, root):
        import mediapipe as mp
        self.mp = mp
        self.mode = None
        if hasattr(mp, "solutions"):
            self._h = mp.solutions.hands.Hands(
                static_image_mode=False, max_num_hands=1, model_complexity=cfg["model_complexity"],
                min_detection_confidence=cfg["min_detection_confidence"],
                min_tracking_confidence=cfg["min_tracking_confidence"])
            self.mode = "solutions"
        else:
            from mediapipe.tasks import python as mpt
            from mediapipe.tasks.python import vision
            path = root / cfg["model_path"]
            if not path.exists():
                raise FileNotFoundError(f"Thiếu model {path} (tải hand_landmarker.task, xem README)")
            opts = vision.HandLandmarkerOptions(
                base_options=mpt.BaseOptions(model_asset_path=str(path)),
                running_mode=vision.RunningMode.VIDEO, num_hands=1,
                min_hand_detection_confidence=cfg["min_detection_confidence"],
                min_tracking_confidence=cfg["min_tracking_confidence"])
            self._h = vision.HandLandmarker.create_from_options(opts)
            self.mode = "tasks"

    def detect(self, rgb, ts_ms: int):
        if self.mode == "solutions":
            res = self._h.process(rgb)
            if not res.multi_hand_landmarks:
                return None, 0.0, ""
            c = res.multi_handedness[0].classification[0]
            return [(p.x, p.y, p.z) for p in res.multi_hand_landmarks[0].landmark], c.score, c.label.lower()
        img = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        res = self._h.detect_for_video(img, ts_ms)
        if not res.hand_landmarks:
            return None, 0.0, ""
        c = res.handedness[0][0]
        return [(p.x, p.y, p.z) for p in res.hand_landmarks[0]], c.score, c.category_name.lower()


class CameraInput(InputDevice):
    name = "camera"

    def __init__(self, cfg: dict, root, force_demo: bool = False):
        self.cfg, self.root, self.force_demo = cfg, root, force_demo
        self._stop = threading.Event()
        self._thread = None

    def start(self, sink):
        self.sink = sink
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------------------------
    def _run(self):
        ccfg = self.cfg["camera"]
        try:
            if self.force_demo:
                raise RuntimeError("bật --demo")
            import cv2
            self.cv2 = cv2
            self.lmk = _Landmarker(ccfg, self.root)
            cap = self._open(cv2, ccfg)
            if cap is None:
                raise RuntimeError(f"không mở được camera index {ccfg['index']}")
        except Exception as e:  # noqa: BLE001
            log.warning("Camera không khả dụng (%s)", e)
            if ccfg.get("demo_fallback", True):
                self._demo_loop()
            else:
                self.sink.set_device("camera", False, str(e))
            return
        self._camera_loop(cap, ccfg)

    def _open(self, cv2, ccfg):
        primary = int(ccfg["index"])
        indexes = [primary] + [i for i in range(5) if i != primary]
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if hasattr(cv2, "CAP_DSHOW") else [cv2.CAP_ANY]
        for index in indexes:
            for backend in backends:
                cap = cv2.VideoCapture(index, backend)
                if not cap.isOpened():
                    cap.release()
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, ccfg["width"])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ccfg["height"])
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ccfg["index"] = index
                log.info("Đã mở camera index %s (backend %s)", index, backend)
                return cap
        return None

    def _camera_loop(self, cap, ccfg):
        cv2 = self.cv2
        pipe = HandPipeline(self.cfg["gesture"], self.sink, simulated=False)
        self.sink.set_device("camera", True, f"webcam #{ccfg['index']} ({self.lmk.mode})", simulated=False)
        fps, last, fails, dropped = 0.0, time.perf_counter(), 0, 0
        last_prev, prev_dt = 0.0, 1.0 / max(1, ccfg["preview_fps"])
        while not self._stop.is_set():
            ok, frame = cap.read()
            t_cap = time.perf_counter()
            if not ok:
                dropped += 1
                fails += 1
                if fails > 30:
                    self.sink.set_device("camera", False, "mất tín hiệu camera")
                    cap.release()
                    while not self._stop.is_set():       # thử mở lại mỗi 2 giây
                        time.sleep(2)
                        cap = self._open(cv2, ccfg)
                        if cap is not None:
                            fails = 0
                            self.sink.set_device("camera", True, "đã kết nối lại", simulated=False)
                            break
                time.sleep(0.01)
                continue
            fails = 0
            if ccfg["flip"]:
                frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            lm, hs, hand = self.lmk.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), int(t_cap * 1000))
            state = pipe.process(lm, hs, hand, t_cap, aspect=w / h)
            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 / max(now - last, 1e-6) if fps else 1 / max(now - last, 1e-6)
            last = now
            if now - last_prev >= prev_dt:
                last_prev = now
                ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, ccfg["jpeg_quality"]])
                self.sink.publish_frame({
                    **state, "hand": hand, "landmarks": [[p[0], p[1]] for p in lm] if lm else None,
                    "jpeg": base64.b64encode(buf.tobytes()).decode() if ok2 else None,
                    "fps": round(fps, 1), "proc_ms": round((now - t_cap) * 1000, 1), "dropped": dropped,
                    "demo": False})
        cap.release()

    def _demo_loop(self):
        """DEMO MODE: bàn tay giả lập chạy qua đúng pipeline nhận diện thật; mọi dữ liệu gắn simulated."""
        pipe = HandPipeline(self.cfg["gesture"], self.sink, simulated=True)
        self.sink.set_device("camera", True, "DEMO MODE (giả lập)", simulated=True)
        fps_t, dt = 30.0, 1 / 30.0
        last_prev, nxt = 0.0, time.perf_counter()
        for label, cx, cy in demo_script(fps_t):
            if self._stop.is_set():
                return
            nxt += dt
            time.sleep(max(0.0, nxt - time.perf_counter()))
            t_cap = time.perf_counter()
            lm = make_hand(cx=cx, cy=cy, **PARAMS[label]) if label else None
            state = pipe.process(lm, 0.99, "right", t_cap)
            if t_cap - last_prev >= 1 / 15:
                last_prev = t_cap
                self.sink.publish_frame({**state, "hand": "right", "jpeg": None, "fps": fps_t, "dropped": 0,
                                         "proc_ms": round((time.perf_counter() - t_cap) * 1000, 2),
                                         "landmarks": [[p[0], p[1]] for p in lm] if lm else None, "demo": True})
