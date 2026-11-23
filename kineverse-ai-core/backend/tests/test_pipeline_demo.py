"""Tích hợp: DEMO camera -> HandPipeline -> InteractionLayer -> UnityClient (WS giả) -> Recorder. Mất ~11 giây."""
import asyncio
import copy
import unittest

from kineverse.server import CoreApp
from tests.helpers import CFG
from tests.test_unity_client import FakeConn, FakeWS


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_script_reaches_unity_with_ack(self):
        cfg = copy.deepcopy(CFG)
        cfg["interaction"]["source_timeout_s"] = 999
        app = CoreApp(cfg, force_demo=True, no_browser=True)
        app.loop = asyncio.get_running_loop()
        ws = FakeWS("ok")
        app.unity._connect_fn = lambda url, **kw: FakeConn(ws)
        utask = asyncio.ensure_future(app.unity.run())
        app.layer.set_device("mouse", True)
        app.camera.start(app)
        for _ in range(100):
            if app.layer.devices["camera"]["connected"]:
                break
            await asyncio.sleep(0.02)
        ok, why = app.layer.set_active("camera")
        self.assertTrue(ok, why)
        await asyncio.sleep(10.5)
        app.camera.stop(); app.unity.stop(); utask.cancel()
        sent = [m["command"] for m in ws.sent if m.get("type") == "interaction"]
        for expected in ["ACTIVATE", "MOVE_RIGHT", "GRAB", "MOVE", "RELEASE", "SELECT", "SWITCH_MODE", "CANCEL"]:
            self.assertIn(expected, sent)
        self.assertEqual(sent.count("MOVE_LEFT"), 0)     # không có swipe ngược ngoài ý muốn
        self.assertEqual(sent.count("GRAB"), 1)          # một lần pinch = một lệnh
        cmds = app.recorder.commands
        self.assertTrue(cmds and all(c["status"] == "ACK" and c["simulated"] for c in cmds))
        s = app.recorder.summary()
        self.assertIn("camera|SIMULATED", s)
        self.assertNotIn("camera|REAL", s)               # dữ liệu giả lập không lẫn vào dữ liệu thật
        print("\nlệnh:", sent, "\nlatency:", s["camera|SIMULATED"]["latency_e2e_ms"])


if __name__ == "__main__":
    unittest.main()
