"""Client WebSocket tới Unity: gửi lệnh, chờ ACK theo message_id, timeout, tự kết nối lại."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .events import Command

log = logging.getLogger("unity")
PROTOCOL = "kineverse-interaction/1.0"


@dataclass
class AckResult:
    status: str                    # ACK | FAILED | TIMEOUT | NOT_CONNECTED
    rtt_ms: float = 0.0
    error: str = ""
    raw: dict = field(default_factory=dict)


class UnityClient:
    def __init__(self, cfg: dict, on_state: Optional[Callable] = None, connect_fn=None):
        u = cfg["unity"]
        self.url, self.ack_timeout, self.reconnect_s = u["url"], u["ack_timeout_s"], u["reconnect_s"]
        self.on_state = on_state or (lambda connected, detail: None)
        self._connect_fn = connect_fn
        self.connected = False
        self.last_command = None
        self.last_response = None
        self.server_info: dict = {}
        self._ws = None
        self._pending: dict = {}
        self._wake = asyncio.Event()
        self._stop = False

    def _connect(self):
        if self._connect_fn:
            return self._connect_fn(self.url, open_timeout=3, ping_interval=None)
        import websockets  # import trễ để test không cần thư viện
        return websockets.connect(self.url, open_timeout=3, ping_interval=None)

    def _set_state(self, connected: bool, detail: str = ""):
        if connected != self.connected or detail:
            self.connected = connected
            self.on_state(connected, detail)

    async def run(self):
        while not self._stop:
            try:
                async with self._connect() as ws:
                    self._ws = ws
                    self._set_state(True, "connected")
                    await ws.send(json.dumps({"type": "connect", "protocol": PROTOCOL,
                                              "client": "kineverse-ai-core", "timestamp": time.time()}))
                    async for raw in ws:
                        await self._handle(raw)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - mọi lỗi mạng đều dẫn tới kết nối lại
                log.debug("Unity connect/recv lỗi: %s", e)
                self._set_state(False, f"{type(e).__name__}")
            finally:
                self._ws = None
                self._fail_pending("disconnected")
                self._set_state(False, "disconnected")
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), self.reconnect_s)
            except asyncio.TimeoutError:
                pass

    async def _handle(self, raw):
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            log.warning("Unity gửi dữ liệu không phải JSON")
            return
        t = msg.get("type")
        if t == "interaction_ack":
            fut = self._pending.get(msg.get("message_id"))
            if fut and not fut.done():
                fut.set_result(msg)
        elif t == "connect_ack":
            self.server_info = msg
        elif t == "ping":
            await self.send_json({"type": "pong", "timestamp": time.time()})

    async def send_json(self, obj: dict) -> bool:
        if not self._ws:
            return False
        try:
            await self._ws.send(json.dumps(obj))
            return True
        except Exception:  # noqa: BLE001
            return False

    def _fail_pending(self, why: str):
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_result({"status": "error", "error_code": why, "error": why, "_local": True})
        self._pending.clear()

    async def send_command(self, cmd: Command) -> AckResult:
        self.last_command = cmd.command
        if not self.connected or not self._ws:
            return AckResult("NOT_CONNECTED", error="unity_not_connected")
        fut = asyncio.get_running_loop().create_future()
        self._pending[cmd.message_id] = fut
        t0 = time.perf_counter()
        if not await self.send_json(cmd.to_wire()):
            self._pending.pop(cmd.message_id, None)
            return AckResult("NOT_CONNECTED", error="send_failed")
        try:
            msg = await asyncio.wait_for(fut, self.ack_timeout)
        except asyncio.TimeoutError:
            self._pending.pop(cmd.message_id, None)
            self.last_response = "TIMEOUT"
            return AckResult("TIMEOUT", (time.perf_counter() - t0) * 1000, "ack_timeout")
        self._pending.pop(cmd.message_id, None)
        rtt = (time.perf_counter() - t0) * 1000
        if msg.get("_local"):
            return AckResult("NOT_CONNECTED", rtt, msg.get("error", ""), msg)
        ok = msg.get("status") == "ok"
        self.last_response = "ACK" if ok else f"FAILED:{msg.get('error_code', '')}"
        return AckResult("ACK" if ok else "FAILED", rtt, msg.get("error", ""), msg)

    def reconnect(self):
        """Yêu cầu kết nối lại ngay (nút Reconnect trên dashboard)."""
        self._wake.set()
        ws = self._ws
        if ws is not None:
            asyncio.ensure_future(ws.close())

    def stop(self):
        self._stop = True
        self._wake.set()
