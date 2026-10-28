"""Self-update the panel from its git checkout.

The panel runs under systemd with Restart=always, so applying an update is:
``git pull`` then exit the process — systemd relaunches it with the new code.
This needs no root because the checkout is owned by the service user.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

# .../panel/mcpanel/updater.py -> repo root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]


def is_git() -> bool:
    return (REPO_ROOT / ".git").exists()


def _git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def check() -> dict:
    """Fetch and report whether the remote is ahead of the local checkout."""
    if not is_git():
        return {"git": False}
    try:
        _git("fetch", "--quiet")
        local = _git("rev-parse", "HEAD").stdout.strip()
        remote = _git("rev-parse", "@{u}").stdout.strip()
        behind = _git("rev-list", "--count", "HEAD..@{u}").stdout.strip() or "0"
        subject = _git("log", "-1", "--format=%s", "@{u}").stdout.strip()
    except Exception as exc:
        return {"git": True, "error": str(exc)}
    return {
        "git": True,
        "update_available": bool(remote) and local != remote,
        "behind": int(behind or 0),
        "current": local[:7],
        "latest": remote[:7],
        "latest_subject": subject,
    }


def apply() -> dict:
    """Pull fast-forward, then restart the service by exiting the process."""
    if not is_git():
        return {"ok": False, "error": "Not a git checkout — update from the host."}
    r = _git("pull", "--ff-only")
    if r.returncode != 0:
        return {"ok": False, "error": (r.stdout + r.stderr).strip()[-600:]}

    def _restart() -> None:
        time.sleep(1)
        os._exit(0)   # systemd (Restart=always) relaunches with the new code

    threading.Thread(target=_restart, daemon=True).start()
    return {"ok": True, "note": "Updated. Panel is restarting — reload in a few seconds."}
