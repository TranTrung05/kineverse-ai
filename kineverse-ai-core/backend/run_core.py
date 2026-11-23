"""Điểm vào: python run_core.py [--with-mock] [--demo] [--glove-mode serial --glove-port COM3]"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kineverse.config import load_config, project_root  # noqa: E402
from kineverse.server import CoreApp  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="KINEVERSE AI Interaction Core")
    ap.add_argument("--config", default=None)
    ap.add_argument("--with-mock", action="store_true", help="chạy Unity Mock Server trong cùng tiến trình")
    ap.add_argument("--demo", action="store_true", help="ép DEMO MODE cho camera (dữ liệu giả lập)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--camera", type=int, default=None, help="chỉ số camera")
    ap.add_argument("--glove-mode", choices=["mock", "serial"], default=None)
    ap.add_argument("--glove-port", default=None)
    a = ap.parse_args()

    cfg = load_config(a.config)
    if a.camera is not None:
        cfg["camera"]["index"] = a.camera
    if a.glove_mode:
        cfg["glove"]["mode"] = a.glove_mode
    if a.glove_port:
        cfg["glove"]["port"] = a.glove_port

    log_dir = project_root() / cfg["log_dir"]
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(log_dir / "core.log", encoding="utf-8")])
    app = CoreApp(cfg, with_mock=a.with_mock, force_demo=a.demo, no_browser=a.no_browser)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("Đã dừng.")


if __name__ == "__main__":
    main()
