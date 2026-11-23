import asyncio
import json
import unittest

from kineverse.events import Command
from kineverse.unity_client import UnityClient
from tests.helpers import CFG


class FakeWS:
    def __init__(self, mode):
        self.q, self.mode, self.sent = asyncio.Queue(), mode, []

    async def send(self, text):
        m = json.loads(text)
        self.sent.append(m)
        if m["type"] == "connect":
            await self.q.put(json.dumps({"type": "connect_ack"}))
        elif m["type"] == "interaction" and self.mode != "silent":
            ack = {"type": "interaction_ack", "message_id": m["message_id"], "status": "ok"}
            if self.mode == "error":
                ack.update(status="error", error_code="X", error="boom")
            await self.q.put(json.dumps(ack))

    def __aiter__(self): return self

    async def __anext__(self):
        v = await self.q.get()
        if v is None:
            raise StopAsyncIteration
        return v

    async def close(self): await self.q.put(None)


class FakeConn:
    def __init__(self, ws): self.ws = ws
    async def __aenter__(self): return self.ws
    async def __aexit__(self, *a): return False


def make_cmd():
    return Command(source="mouse", command="GRAB", payload={}, t_capture=0.0)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def _client(self, mode):
        cfg = json.loads(json.dumps(CFG)); cfg["unity"]["ack_timeout_s"] = 0.2
        ws = FakeWS(mode)
        c = UnityClient(cfg, connect_fn=lambda url, **kw: FakeConn(ws))
        task = asyncio.ensure_future(c.run())
        for _ in range(50):
            if c.connected:
                break
            await asyncio.sleep(0.01)
        return c, ws, task

    async def _close(self, c, task):
        c.stop(); task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_ack(self):
        c, ws, t = await self._client("ok")
        r = await c.send_command(make_cmd())
        self.assertEqual(r.status, "ACK")
        self.assertEqual(ws.sent[-1]["type"], "interaction")
        self.assertEqual(c.last_response, "ACK")
        await self._close(c, t)

    async def test_failed(self):
        c, _, t = await self._client("error")
        r = await c.send_command(make_cmd())
        self.assertEqual((r.status, r.error), ("FAILED", "boom"))
        await self._close(c, t)

    async def test_timeout(self):
        c, _, t = await self._client("silent")
        r = await c.send_command(make_cmd())
        self.assertEqual(r.status, "TIMEOUT")
        await self._close(c, t)

    async def test_not_connected(self):
        c = UnityClient(CFG)
        self.assertEqual((await c.send_command(make_cmd())).status, "NOT_CONNECTED")


if __name__ == "__main__":
    unittest.main()
