"""Ghi dữ liệu thực nghiệm: log sự kiện/lệnh, nhiệm vụ, thống kê độ trễ (trung bình, P95), xuất CSV/JSON.

Dữ liệu từ DEMO MODE/mock được gắn simulated=true và tách riêng trong summary: KHÔNG dùng làm kết quả nghiên cứu.
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional


def percentile(values, p: float) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def _avg(values):
    return sum(values) / len(values) if values else None


def _r(x, n=2):
    return None if x is None else round(x, n)


class Recorder:
    def __init__(self, data_dir):
        self.root = Path(data_dir)
        self.session = time.strftime("%Y%m%d_%H%M%S")
        self.t_start = time.time()
        self.events: list = []
        self.commands: list = []
        self.tasks: list = []
        self._task: Optional[dict] = None
        self.counters: Counter = Counter()     # (source, simulated, name)
        self._last_cmd_idx: Optional[int] = None

    # ---- ghi nhận -------------------------------------------------------------------
    def log_decision(self, d):
        ev = d.event
        self.events.append({"time": round(ev.timestamp, 3), "event_id": ev.event_id, "source": ev.source,
                            "simulated": ev.simulated, "action": ev.action, "confidence": round(ev.confidence, 3),
                            "accepted": d.accepted, "reason": d.reason})

    def log_command(self, cmd, status: str, rtt_ms: float, e2e_ms: float, proc_ms: float):
        self.commands.append({"time": round(cmd.timestamp, 3), "message_id": cmd.message_id, "source": cmd.source,
                              "simulated": cmd.simulated, "command": cmd.command,
                              "confidence": round(cmd.confidence, 3), "status": status,
                              "processing_ms": round(proc_ms, 2), "rtt_ms": round(rtt_ms, 2),
                              "e2e_ms": round(e2e_ms, 2), "misread": False})
        self._last_cmd_idx = len(self.commands) - 1

    def note(self, source: str, simulated: bool, name: str):
        self.counters[(source, simulated, name)] += 1

    def mark_misread(self) -> bool:
        """Người vận hành đánh dấu lệnh gần nhất là nhận diện sai."""
        if self._last_cmd_idx is None or self.commands[self._last_cmd_idx]["misread"]:
            return False
        c = self.commands[self._last_cmd_idx]
        c["misread"] = True
        self.note(c["source"], c["simulated"], "misread")
        return True

    def mark_retry(self, source: str, simulated: bool = False):
        self.note(source, simulated, "retry")
        if self._task:
            self._task["retries"] += 1

    def start_task(self, name: str, source: str, simulated: bool = False):
        self._task = {"name": name, "source": source, "simulated": simulated, "t0": time.perf_counter(),
                      "retries": 0, "start_time": round(time.time(), 3)}

    def end_task(self, success: bool) -> Optional[dict]:
        t = self._task
        if not t:
            return None
        t["duration_s"] = round(time.perf_counter() - t.pop("t0"), 3)
        t["success"] = bool(success)
        self.tasks.append(t)
        self._task = None
        return t

    # ---- thống kê -------------------------------------------------------------------
    def summary(self) -> dict:
        groups = defaultdict(lambda: {"events": [], "cmds": [], "tasks": []})
        for e in self.events:
            groups[(e["source"], e["simulated"])]["events"].append(e)
        for c in self.commands:
            groups[(c["source"], c["simulated"])]["cmds"].append(c)
        for t in self.tasks:
            groups[(t["source"], t["simulated"])]["tasks"].append(t)
        for (s, sim, _n) in self.counters:
            groups[(s, sim)]
        out = {}
        for (src, sim), g in sorted(groups.items()):
            cmds, evs, tasks = g["cmds"], g["events"], g["tasks"]
            ok = [c for c in cmds if c["status"] == "ACK"]
            e2e = [c["e2e_ms"] for c in ok]
            cnt = lambda n: self.counters.get((src, sim, n), 0)
            n_cmd = len(cmds)
            misread = cnt("misread")
            out[f"{src}|{'SIMULATED' if sim else 'REAL'}"] = {
                "source": src, "simulated": sim,
                "total_events": len(evs), "accepted_events": sum(1 for e in evs if e["accepted"]),
                "commands_sent": n_cmd, "ack_ok": len(ok),
                "failed": sum(1 for c in cmds if c["status"] == "FAILED"),
                "timeouts": sum(1 for c in cmds if c["status"] == "TIMEOUT"),
                "not_connected": sum(1 for c in cmds if c["status"] == "NOT_CONNECTED"),
                "success_rate": _r(len(ok) / n_cmd, 4) if n_cmd else None,
                "misreads_marked": misread,
                "recognition_accuracy_operator_marked": _r(1 - misread / n_cmd, 4) if n_cmd else None,
                "retries": cnt("retry"), "tracking_lost": cnt("tracking_lost"),
                "latency_e2e_ms": {"mean": _r(_avg(e2e)), "p50": _r(percentile(e2e, 50)),
                                   "p95": _r(percentile(e2e, 95)), "max": _r(max(e2e) if e2e else None)},
                "processing_ms_mean": _r(_avg([c["processing_ms"] for c in cmds])),
                "tasks": len(tasks), "task_success": sum(1 for t in tasks if t["success"]),
                "task_time_mean_s": _r(_avg([t["duration_s"] for t in tasks])),
            }
        return out

    def export(self) -> Path:
        d = self.root / f"session_{self.session}"
        d.mkdir(parents=True, exist_ok=True)

        def dump(name, rows):
            if not rows:
                return
            keys = list(rows[0].keys())
            with open(d / name, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(rows)

        dump("events.csv", self.events)
        dump("commands.csv", self.commands)
        dump("tasks.csv", self.tasks)
        with open(d / "summary.json", "w", encoding="utf-8") as f:
            json.dump({"session": self.session, "duration_s": round(time.time() - self.t_start, 1),
                       "note": "Nhóm SIMULATED là dữ liệu mô phỏng (demo/mock), không dùng làm kết quả nghiên cứu.",
                       "groups": self.summary()}, f, ensure_ascii=False, indent=2)
        return d
