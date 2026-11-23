"""Unity Mock Server: mô phỏng phía Unity nhận lệnh và phản hồi ACK.

Chạy độc lập:  python -m kineverse.mock_unity --port 8766 [--delay-ms 20] [--fail-rate 0.1] [--drop-rate 0.1]
- fail-rate: tỷ lệ trả status=error (kiểm thử "command failed")
- drop-rate: tỷ lệ KHÔNG trả ACK (kiểm thử timeout)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import time

log = logging.getLogger("mock_unity")
PROTOCOL = "kineverse-interaction/1.0"


class VirtualObject:
    """Trạng thái đối tượng ảo trong mock (chỉ để in log, KHÔNG phải mô phỏng 3D)."""

    def __init__(self):
        self.pos, self.rot, self.scale, self.grabbed, self.mode = [0.0, 0.0], 0.0, 1.0, False, 0

    def apply(self, cmd: str, payload: dict):
        step = 0.1
        if cmd == "GRAB":
            self.grabbed = True
        elif cmd == "RELEASE":
            self.grabbed = False
        elif cmd == "MOVE_LEFT":
            self.pos[0] -= step
        elif cmd == "MOVE_RIGHT":
            self.pos[0] += step
        elif cmd == "MOVE_UP":
            self.pos[1] += step
        elif cmd == "MOVE_DOWN":
            self.pos[1] -= step
        elif cmd == "MOVE":
            self.pos[0] += float(payload.get("dx", 0)); self.pos[1] += float(payload.get("dy", 0))
        elif cmd == "ROTATE":
            self.rot += float(payload.get("dx", 5))
        elif cmd == "SCALE":
            self.scale = max(0.1, self.scale + float(payload.get("delta", 0)))
        elif cmd == "SWITCH_MODE":
            self.mode = (self.mode + 1) % 3
        elif cmd in ("RESET", "CANCEL"):
            self.__init__()

    def snapshot(self):
        return {"pos": [round(v, 2) for v in self.pos], "rot": round(self.rot, 1), "scale": round(self.scale, 2),
                "grabbed": self.grabbed, "mode": self.mode}


def make_handler(delay_ms=0.0, fail_rate=0.0, drop_rate=0.0, seed=None, quiet=False):
    rng = random.Random(seed)
    obj = VirtualObject()

    async def handler(ws, path=None):
        path = path or getattr(ws, "path", None) or getattr(getattr(ws, "request", None), "path", "/")
        if path != "/interaction":
            await ws.close(1008, "unknown path")
            return
        log.info("Client kết nối: %s", path)
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            t = msg.get("type")
            if t == "connect":
                await ws.send(json.dumps({"type": "connect_ack", "protocol": PROTOCOL, "server": "unity-mock",
                                          "timestamp": time.time()}))
            elif t == "interaction":
                if rng.random() < drop_rate:
                    if not quiet:
                        log.info("DROP  %s %s (không ACK)", msg.get("message_id"), msg.get("command"))
                    continue
                if delay_ms:
                    await asyncio.sleep(delay_ms / 1000.0)
                ack = {"type": "interaction_ack", "message_id": msg.get("message_id"), "status": "ok",
                       "timestamp": time.time()}
                if rng.random() < fail_rate:
                    ack.update(status="error", error_code="MOCK_FAILURE", error="lỗi giả lập")
                else:
                    obj.apply(msg.get("command", ""), msg.get("payload", {}))
                    ack["state"] = obj.snapshot()
                if not quiet:
                    log.info("%-8s %-12s from=%-6s -> %s %s", msg.get("message_id"), msg.get("command"),
                             msg.get("source"), ack["status"], obj.snapshot())
                await ws.send(json.dumps(ack))
            elif t in ("device_status", "system_status"):
                pass
            elif t == "pong":
                pass

    return handler


async def serve(port=8766, host="127.0.0.1", **kw):
    import websockets
    return await websockets.serve(make_handler(**kw), host, port)


def main():
    ap = argparse.ArgumentParser(description="KINEVERSE Unity Mock Server")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--delay-ms", type=float, default=15.0)
    ap.add_argument("--fail-rate", type=float, default=0.0)
    ap.add_argument("--drop-rate", type=float, default=0.0)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    async def _run():
        await serve(a.port, delay_ms=a.delay_ms, fail_rate=a.fail_rate, drop_rate=a.drop_rate)
        log.info("Unity Mock đang chạy: ws://127.0.0.1:%d/interaction  (Ctrl+C để dừng)", a.port)
        await asyncio.Future()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
