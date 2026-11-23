"""Nạp cấu hình: config.json ghi đè lên giá trị mặc định (deep merge)."""
import copy
import json
import sys
from pathlib import Path


def project_root() -> Path:
    """Thư mục gốc dự án (hỗ trợ cả khi đóng gói bằng PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path=None) -> dict:
    path = Path(path) if path else project_root() / "config.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
