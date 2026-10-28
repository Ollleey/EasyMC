"""Run the playit.gg agent so friends can join without port forwarding.

On first start the agent prints a claim URL (open it to link the tunnel to a
playit.gg account and point a tunnel at 127.0.0.1:<server port>). The agent's
output — including the claim URL and the public address — is captured into a
ring buffer shown in the panel.

The binary is downloaded once into the data dir.
"""
from __future__ import annotations

import collections
import platform
import stat
import subprocess
import threading
from pathlib import Path

import httpx

from . import config

_RELEASE = "https://github.com/playit-cloud/playit-agent/releases/latest/download"
_OUTPUT_LINES = 200


class Tunnel:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._out: collections.deque[str] = collections.deque(maxlen=_OUTPUT_LINES)
        self._lock = threading.Lock()

    def _binary(self) -> Path:
        arch = "aarch64" if platform.machine() in ("aarch64", "arm64") else "amd64"
        return config.DATA_DIR / f"playit-linux-{arch}"

    def _ensure_binary(self) -> Path:
        binp = self._binary()
        if not binp.exists():
            self._append(f"[panel] Downloading playit agent ({binp.name})...")
            url = f"{_RELEASE}/{binp.name}"
            with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as r:
                r.raise_for_status()
                with binp.open("wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
            binp.chmod(binp.stat().st_mode | stat.S_IEXEC)
        return binp

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.is_running():
            return
        binp = self._ensure_binary()
        self._append("[panel] Starting playit tunnel...")
        self._proc = subprocess.Popen(
            [str(binp)], cwd=str(config.DATA_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._append("[panel] Tunnel stopped.")

    def output(self) -> str:
        with self._lock:
            return "\n".join(self._out)

    def _pump(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for line in self._proc.stdout:
            self._append(line.rstrip("\n"))

    def _append(self, line: str) -> None:
        with self._lock:
            self._out.append(line)


tunnel = Tunnel()
