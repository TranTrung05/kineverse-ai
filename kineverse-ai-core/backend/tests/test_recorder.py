import tempfile
import unittest
from pathlib import Path

from kineverse.events import Command
from kineverse.interaction import Decision
from kineverse.events import InputEvent
from kineverse.recorder import Recorder, percentile


def cmd(src="camera", sim=False, name="GRAB"):
    return Command(source=src, command=name, payload={}, t_capture=0.0, simulated=sim, confidence=0.9)


class RecorderTests(unittest.TestCase):
    def test_percentile(self):
        self.assertIsNone(percentile([], 95))
        self.assertAlmostEqual(percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertAlmostEqual(percentile(list(range(1, 101)), 95), 95.05)

    def test_summary_separates_simulated(self):
        r = Recorder(tempfile.mkdtemp())
        r.log_command(cmd(sim=True), "ACK", 10, 100, 90)
        r.log_command(cmd(sim=False), "ACK", 10, 200, 190)
        r.log_command(cmd(sim=False), "TIMEOUT", 1000, 1100, 100)
        s = r.summary()
        self.assertIn("camera|SIMULATED", s)
        real = s["camera|REAL"]
        self.assertEqual(real["commands_sent"], 2)
        self.assertEqual(real["timeouts"], 1)
        self.assertEqual(real["latency_e2e_ms"]["mean"], 200.0)      # timeout không tính vào độ trễ
        self.assertEqual(real["success_rate"], 0.5)

    def test_misread_and_tasks(self):
        r = Recorder(tempfile.mkdtemp())
        r.log_command(cmd(), "ACK", 5, 50, 45)
        self.assertTrue(r.mark_misread())
        self.assertFalse(r.mark_misread())                            # không đánh dấu hai lần
        r.start_task("A", "camera"); r.mark_retry("camera"); t = r.end_task(True)
        self.assertEqual(t["retries"], 1)
        s = r.summary()["camera|REAL"]
        self.assertEqual(s["misreads_marked"], 1)
        self.assertEqual(s["recognition_accuracy_operator_marked"], 0.0)
        self.assertEqual(s["tasks"], 1)

    def test_export_files(self):
        r = Recorder(tempfile.mkdtemp())
        e = InputEvent(source="camera", type="gesture", action="GRAB", confidence=.9)
        r.log_decision(Decision(True, "ok", e)); r.log_command(cmd(), "ACK", 5, 50, 45)
        d = r.export()
        for f in ("events.csv", "commands.csv", "summary.json"):
            self.assertTrue((Path(d) / f).exists(), f)


if __name__ == "__main__":
    unittest.main()
