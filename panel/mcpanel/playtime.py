"""Track per-player playtime from join/leave events.

Totals persist in ``playtime.json`` under the data dir. Time accrues while the
panel is running and observing the server console. Players currently online
have their running session added to the displayed total.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from . import config

_lock = threading.Lock()


def _path() -> Path:
    return config.DATA_DIR / "playtime.json"


def _load() -> dict:
    p = _path()
    if not p.exists():
        return {"totals": {}, "online": {}}
    try:
        data = json.loads(p.read_text())
        data.setdefault("totals", {})
        data.setdefault("online", {})
        return data
    except (ValueError, OSError):
        return {"totals": {}, "online": {}}


def _save(data: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(_path())


def record_join(name: str) -> None:
    with _lock:
        data = _load()
        data["online"][name] = time.time()
        _save(data)


def record_leave(name: str) -> None:
    with _lock:
        data = _load()
        start = data["online"].pop(name, None)
        if start is not None:
            data["totals"][name] = data["totals"].get(name, 0) + (time.time() - start)
        _save(data)


def snapshot() -> list[dict]:
    """Players sorted by total playtime, including the running session."""
    with _lock:
        data = _load()
    now = time.time()
    rows = []
    names = set(data["totals"]) | set(data["online"])
    for name in names:
        total = data["totals"].get(name, 0)
        online = name in data["online"]
        if online:
            total += now - data["online"][name]
        rows.append({"name": name, "seconds": int(total), "online": online})
    rows.sort(key=lambda r: r["seconds"], reverse=True)
    return rows
