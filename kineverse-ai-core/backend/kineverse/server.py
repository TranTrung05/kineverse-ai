"""CoreApp: điều phối thiết bị -> Interaction Layer -> Unity, và phát dữ liệu realtime cho dashboard."""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import threading
import time
import webbrowser
from collections import deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from .config import project_root
from .events import Command, InputEvent
from .inputs.camera import CameraInput
from .inputs.glove import GloveInput
from .inputs.mouse import MouseInput
from .interaction import InteractionLayer
from .recorder import Recorder, percentile
from .unity_client import UnityClient

log = logging.getLogger("core")


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class CoreApp:
    def __init__(self, cfg: dict, with_mock=False, force_demo=False, no_browser=False):
        self.cfg, self.with_mock, self.no_browser = cfg, with_mock, no_browser
        root = project_root()
        self.root = root
        self.layer = InteractionLayer(cfg)
        self.recorder = Recorder(root / cfg["data_dir"])
        self.unity = UnityClient(cfg, on_state=self._on_unity_state)
        self.mouse = MouseInput()
        self.camera = CameraInput(cfg, root, force_demo=force_demo)
        self.glove = GloveInput(cfg, root / cfg["data_dir"])
        self.devices = {"camera": self.camera, "glove": self.glove, "mouse": self.mouse}
        self.clients: set = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.e2e = deque(maxlen=200)
        self.in_flight = 0
        self.dropped_commands = 0
        self.last_frame: dict = {}
        self.unity_detail = "connecting"
        self.messages: deque = deque(maxlen=50)

    # ---- API cho thiết bị (sink) -------------------------------------------------
    def emit(self, ev: InputEvent):
        """Thread-safe."""
        if self.loop:
            self.loop.call_soon_threadsafe(self.emit_local, ev)

    def emit_local(self, ev: InputEvent):
        d = self.layer.handle(ev)
        self.recorder.log_decision(d)
        self._broadcast({"type": "decision", "accepted": d.accepted, "reason": d.reason, "event": ev.to_dict()})
        if d.accepted:
            if self.in_flight >= self.cfg["interaction"]["max_in_flight"]:
                self.dropped_commands += 1
                return
            self.in_flight += 1
            asyncio.ensure_future(self._dispatch(d.command))

    def set_device(self, source, connected, detail="", simulated=None):
        if self.loop:
            self.loop.call_soon_threadsafe(self._set_device, source, connected, detail, simulated)

    def _set_device(self, source, connected, detail, simulated):
        self.layer.set_device(source, connected, detail, simulated)
        self._broadcast_status()

    def note(self, source, simulated, name):
        if self.loop:
            self.loop.call_soon_threadsafe(self.recorder.note, source, simulated, name)
            if name == "tracking_lost":
                self.loop.call_soon_threadsafe(self._broadcast, {"type": "info", "text": "TRACKING LOST"})

    def publish_frame(self, frame: dict):
        if self.loop:
            self.loop.call_soon_threadsafe(self._on_frame, frame)

    def log_info(self, text: str):
        log.info(text)
        if self.loop:
            self.loop.call_soon_threadsafe(self._broadcast, {"type": "info", "text": text})

    def _on_frame(self, frame: dict):
        self.last_frame = {k: v for k, v in frame.items() if k != "jpeg"}
        self._broadcast({"type": "frame", **frame})

    # ---- gửi lệnh Unity --------------------------------------------------------------
    async def _dispatch(self, cmd: Command):
        try:
            self._broadcast({"type": "command_sent", "message_id": cmd.message_id, "command": cmd.command,
                             "source": cmd.source, "simulated": cmd.simulated, "event_id": cmd.event_id})
            res = await self.unity.send_command(cmd)
            now = time.perf_counter()
            e2e = (now - cmd.t_capture) * 1000.0
            proc = (e2e - res.rtt_ms) if res.rtt_ms else 0.0
            if res.status == "ACK":
                self.e2e.append(e2e)
            self.recorder.log_command(cmd, res.status, res.rtt_ms, e2e, max(proc, 0.0))
            self._broadcast({"type": "command_result", "message_id": cmd.message_id, "command": cmd.command,
                             "source": cmd.source, "status": res.status, "rtt_ms": round(res.rtt_ms, 1),
                             "e2e_ms": round(e2e, 1), "error": res.error, "simulated": cmd.simulated,
                             "event_id": cmd.event_id,
                             "state": res.raw.get("state")})
        finally:
            self.in_flight -= 1

    def _on_unity_state(self, connected: bool, detail: str):
        self.unity_detail = detail
        self._broadcast_status()

    # ---- dashboard -------------------------------------------------------------------
    def _broadcast(self, msg: dict):
        if not self.clients:
            return
        text = json.dumps(msg, ensure_ascii=False)
        import websockets
        try:
            websockets.broadcast(self.clients, text)
        except Exception:  # noqa: BLE001
            log.exception("broadcast lỗi")

    def status_snapshot(self) -> dict:
        lat = list(self.e2e)
        devs = {}
        for s, d in self.layer.devices.items():
            devs[s] = {"connected": d["connected"], "detail": d["detail"], "simulated": d["simulated"]}
        f = self.last_frame
        return {
            "type": "status", "active_source": self.layer.active, "devices": devs,
            "unity": {"connected": self.unity.connected, "endpoint": self.unity.url, "detail": self.unity_detail,
                      "last_command": self.unity.last_command, "last_response": self.unity.last_response},
            "perf": {"fps": f.get("fps", 0), "proc_ms": f.get("proc_ms", 0), "dropped_frames": f.get("dropped", 0),
                     "e2e_mean_ms": round(sum(lat) / len(lat), 1) if lat else None,
                     "e2e_p95_ms": round(percentile(lat, 95), 1) if lat else None,
                     "in_flight": self.in_flight, "dropped_commands": self.dropped_commands},
            "demo": bool(f.get("demo")) or any(d["simulated"] for s, d in self.layer.devices.items()
                                               if s == self.layer.active and d["connected"]),
            "stats": dict(self.layer.stats),
        }

    def _broadcast_status(self):
        self._broadcast(self.status_snapshot())

    async def _ws_handler(self, ws, path=None):
        self.clients.add(ws)
        try:
            await ws.send(json.dumps({**self.status_snapshot(), "type": "status"}))
            await ws.send(json.dumps({"type": "summary", "groups": self.recorder.summary()}))
            async for raw in ws:
                try:
                    await self._on_dashboard_msg(json.loads(raw))
                except Exception:  # noqa: BLE001
                    log.exception("Lỗi xử lý thông điệp dashboard")
        finally:
            self.clients.discard(ws)

    async def _on_dashboard_msg(self, m: dict):
        t = m.get("type")
        if t == "set_source":
            old = self.layer.active
            ok, why = self.layer.set_active(m.get("source"))
            self._broadcast({"type": "source_changed", "ok": ok, "reason": why, "from": old,
                             "to": self.layer.active, "by": "user"})
            self._broadcast_status()
        elif t == "mouse":
            self.mouse.submit(m.get("action", ""), m.get("payload", {}))
        elif t == "unity_reconnect":
            self.unity.reconnect()
        elif t == "glove_calibrate":
            self.glove.calibrate()
            self.log_info(f"Calibration găng tay: xòe tay rồi nắm chặt chậm trong {self.cfg['glove']['calibration_s']}s")
        elif t == "task_start":
            d = self.layer.devices[self.layer.active]
            self.recorder.start_task(str(m.get("name", "task")), self.layer.active, d["simulated"])
            self.log_info("TASK STARTED")
        elif t == "task_end":
            r = self.recorder.end_task(bool(m.get("success", True)))
            self._broadcast({"type": "task_done", "task": r})
        elif t == "mark_misread":
            ok = self.recorder.mark_misread()
            self.log_info("Đã đánh dấu nhận diện sai" if ok else "Không có lệnh để đánh dấu")
        elif t == "mark_retry":
            d = self.layer.devices[self.layer.active]
            self.recorder.mark_retry(self.layer.active, d["simulated"])
            self.log_info("Đã ghi nhận 1 lần thao tác lại")
        elif t == "export":
            path = self.recorder.export()
            self._broadcast({"type": "exported", "path": str(path)})
        elif t == "get_summary":
            self._broadcast({"type": "summary", "groups": self.recorder.summary()})

    async def _status_loop(self):
        n = 0
        while True:
            await asyncio.sleep(1.0)
            fo = self.layer.check_failover()
            if fo:
                self._broadcast({"type": "source_changed", "ok": True, "from": fo[0], "to": fo[1], "by": "failover"})
                self.log_info(f"Failover nguồn điều khiển: {fo[0]} -> {fo[1]}")
            snap = self.status_snapshot()
            self._broadcast(snap)
            if self.unity.connected:
                await self.unity.send_json({"type": "device_status", "timestamp": time.time(),
                                            "active_source": snap["active_source"], "devices": snap["devices"]})
                await self.unity.send_json({"type": "system_status", "timestamp": time.time(), **snap["perf"]})
            n += 1
            if n % 3 == 0:
                self._broadcast({"type": "summary", "groups": self.recorder.summary()})

    # ---- khởi chạy -------------------------------------------------------------------
    def _start_http(self):
        d = self.root / "dashboard"
        handler = functools.partial(_QuietHandler, directory=str(d))
        port = self.cfg["dashboard"]["http_port"]
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="http").start()
        return f"http://127.0.0.1:{port}/index.html"

    async def run(self):
        import websockets
        self.loop = asyncio.get_running_loop()
        url = self._start_http()
        wsport = self.cfg["dashboard"]["ws_port"]
        await websockets.serve(self._ws_handler, "127.0.0.1", wsport)
        if self.with_mock:
            from .mock_unity import serve
            await serve(int(self.cfg["unity"]["url"].rsplit(":", 1)[1].split("/")[0]), delay_ms=15, quiet=True)
            log.info("Unity Mock chạy trong cùng tiến trình")
        asyncio.ensure_future(self.unity.run())
        asyncio.ensure_future(self._status_loop())
        for d in self.devices.values():
            d.start(self)
        log.info("Dashboard: %s  (WS %d)", url, wsport)
        if self.cfg["dashboard"]["open_browser"] and not self.no_browser:
            webbrowser.open(url)
        await asyncio.Future()
