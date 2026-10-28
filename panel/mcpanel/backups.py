"""World backups: create, list, delete, restore, plus an auto-backup thread.

A backup is a ``.tar.gz`` of the world directories and ``server.properties``
stored under the data dir's ``backups/`` folder. Retention keeps the newest
``backup_keep`` files.
"""
from __future__ import annotations

import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config

_WORLDS = ("world", "world_nether", "world_the_end")
_lock = threading.Lock()
_state = {"last_backup": None, "last_result": ""}


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def create_backup(label: str = "manual") -> Path:
    """Create a backup archive and return its path. Thread-safe."""
    with _lock:
        config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{_timestamp()}-{label}.tar.gz"
        dest = config.BACKUP_DIR / name
        server = config.SERVER_DIR
        tmp = dest.with_suffix(".tmp")
        with tarfile.open(tmp, "w:gz") as tar:
            for world in _WORLDS:
                wdir = server / world
                if wdir.exists():
                    tar.add(wdir, arcname=world)
            props = server / "server.properties"
            if props.exists():
                tar.add(props, arcname="server.properties")
        tmp.replace(dest)
        _state["last_backup"] = datetime.now(timezone.utc).isoformat()
        _state["last_result"] = f"Created {name} ({dest.stat().st_size // 1024} KiB)"
        return dest


def list_backups() -> list[dict]:
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(config.BACKUP_DIR.glob("*.tar.gz"), reverse=True):
        st = f.stat()
        out.append({
            "name": f.name,
            "size_mb": round(st.st_size / (1024 * 1024), 2),
            "created": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        })
    return out


def delete_backup(name: str) -> None:
    safe = Path(name).name
    (config.BACKUP_DIR / safe).unlink(missing_ok=True)


def prune(keep: int) -> int:
    """Delete all but the newest ``keep`` backups. Returns how many removed."""
    files = sorted(config.BACKUP_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    removed = 0
    for f in files[max(keep, 0):]:
        f.unlink(missing_ok=True)
        removed += 1
    return removed


def restore_backup(name: str) -> None:
    """Extract a backup over the server dir. Caller must stop the server first."""
    safe = Path(name).name
    src = config.BACKUP_DIR / safe
    if not src.exists():
        raise RuntimeError(f"Backup not found: {safe}")
    # Clear existing worlds so a smaller restored world doesn't keep stale chunks.
    for world in _WORLDS:
        wdir = config.SERVER_DIR / world
        if wdir.exists():
            import shutil
            shutil.rmtree(wdir, ignore_errors=True)
    with tarfile.open(src, "r:gz") as tar:
        tar.extractall(config.SERVER_DIR, filter="data")


def state() -> dict:
    return dict(_state)


# --------------------------------------------------------------------------
# Auto-backup thread
# --------------------------------------------------------------------------
class AutoBackup(threading.Thread):
    """Background loop that backs up on the configured interval."""

    def __init__(self, get_settings) -> None:
        super().__init__(daemon=True)
        self._get_settings = get_settings
        self._stop = threading.Event()
        self._next_run = 0.0

    def run(self) -> None:
        # Stagger the first run so a fresh install isn't backed up empty.
        self._next_run = time.time() + 300
        while not self._stop.wait(60):
            s = self._get_settings()
            if not s.backup_enabled:
                continue
            if time.time() >= self._next_run:
                try:
                    create_backup(label="auto")
                    prune(s.backup_keep)
                except Exception as exc:  # never let the thread die
                    _state["last_result"] = f"Auto-backup failed: {exc}"
                self._next_run = time.time() + max(1, s.backup_interval_hours) * 3600

    def stop(self) -> None:
        self._stop.set()
