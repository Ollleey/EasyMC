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
    # -c safe.directory avoids "dubious ownership" when the checkout was
    # touched as another user (e.g. a manual root `git pull`).
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "-c", f"safe.directory={REPO_ROOT}", *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _upstream() -> str:
    """The tracking ref, falling back to origin/main."""
    r = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ref = r.stdout.strip()
    return ref if r.returncode == 0 and ref else "origin/main"


def check() -> dict:
    """Fetch and report whether the remote is ahead of the local checkout.

    Any git failure is surfaced as ``error`` instead of being silently
    reported as up-to-date.
    """
    if not is_git():
        return {"git": False}
    f = _git("fetch", "--quiet")
    if f.returncode != 0:
        return {"git": True, "error": "git fetch failed: " + (f.stderr.strip() or "unknown")[:300]}

    upstream = _upstream()
    local = _git("rev-parse", "HEAD")
    remote = _git("rev-parse", upstream)
    if local.returncode != 0 or remote.returncode != 0:
        return {"git": True, "error": f"cannot resolve {upstream}: " +
                (remote.stderr.strip() or local.stderr.strip() or "unknown")[:300]}

    local_sha, remote_sha = local.stdout.strip(), remote.stdout.strip()
    behind = _git("rev-list", "--count", f"HEAD..{upstream}").stdout.strip() or "0"
    subject = _git("log", "-1", "--format=%s", upstream).stdout.strip()
    return {
        "git": True,
        "update_available": local_sha != remote_sha,
        "behind": int(behind) if behind.isdigit() else 0,
        "current": local_sha[:7],
        "latest": remote_sha[:7],
        "latest_subject": subject,
    }


def apply() -> dict:
    """Pull fast-forward, then restart the service by exiting the process."""
    if not is_git():
        return {"ok": False, "error": "Not a git checkout — update from the host."}
    upstream = _upstream()
    remote = upstream.split("/", 1)
    r = (_git("pull", "--ff-only", remote[0], remote[1]) if len(remote) == 2
         else _git("pull", "--ff-only"))
    if r.returncode != 0:
        return {"ok": False, "error": (r.stdout + r.stderr).strip()[-600:]}

    def _restart() -> None:
        time.sleep(1)
        os._exit(0)   # systemd (Restart=always) relaunches with the new code

    threading.Thread(target=_restart, daemon=True).start()
    return {"ok": True, "note": "Updated. Panel is restarting — reload in a few seconds."}
