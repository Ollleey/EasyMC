"""Run the Minecraft server as a child process and expose control + console.

A single server instance is managed. The process stdout is streamed into a
bounded ring buffer so the web console stays cheap, and commands are written
to stdin. An optional watchdog thread restarts the server if it dies while
``auto_restart`` is on.

Extras: an ``on_event`` hook fires on start/stop/crash and player join/leave
(used for Discord notifications), live RAM/uptime stats, and RCON-backed
queries so stat polling doesn't clutter the console.
"""
from __future__ import annotations

import collections
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from . import config, loaders, rcon

_CONSOLE_LINES = 500
_JOIN_LEAVE = re.compile(r"\]:\s+(\w{1,16}) (joined|left) the game")


class ServerManager:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._console: collections.deque[str] = collections.deque(maxlen=_CONSOLE_LINES)
        self._lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._want_running = False
        self._status = "stopped"  # stopped | starting | running | crashed
        self._started_at = 0.0
        self._settings: config.Settings | None = None
        self.on_event = None       # callable(event_type: str, message: str)
        self._cpu_prev: tuple[int, int] | None = None   # (proc_jiffies, total_jiffies)

    # -- introspection ------------------------------------------------------
    @property
    def status(self) -> str:
        if self._proc and self._proc.poll() is None:
            return "running"
        return self._status

    def console_text(self) -> str:
        with self._lock:
            return "\n".join(self._console)

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stats(self) -> dict:
        """Live RAM (MiB), CPU (% of total machine) and uptime (seconds)."""
        rss_mb, uptime, cpu = 0, 0, 0
        if self.is_running() and self._proc is not None:
            uptime = int(time.time() - self._started_at)
            pid = self._proc.pid
            try:
                with open(f"/proc/{pid}/statm") as fh:
                    resident_pages = int(fh.read().split()[1])
                rss_mb = resident_pages * os.sysconf("SC_PAGE_SIZE") // (1024 * 1024)
            except (OSError, ValueError, IndexError):
                rss_mb = 0
            cpu = self._cpu_percent(pid)
        else:
            self._cpu_prev = None
        return {"rss_mb": rss_mb, "uptime_s": uptime, "cpu_pct": cpu}

    def _cpu_percent(self, pid: int) -> int:
        """CPU use of the process as a percentage of the whole machine."""
        try:
            with open(f"/proc/{pid}/stat") as fh:
                parts = fh.read().rsplit(")", 1)[1].split()
            proc_j = int(parts[11]) + int(parts[12])          # utime + stime
            with open("/proc/stat") as fh:
                total_j = sum(int(x) for x in fh.readline().split()[1:])
        except (OSError, ValueError, IndexError):
            return 0
        prev = self._cpu_prev
        self._cpu_prev = (proc_j, total_j)
        if prev is None:
            return 0
        d_proc, d_total = proc_j - prev[0], total_j - prev[1]
        if d_total <= 0:
            return 0
        return max(0, min(100, round(d_proc * 100 / d_total)))

    # -- lifecycle ----------------------------------------------------------
    def start(self, settings: config.Settings) -> None:
        if self.is_running():
            return
        server_dir = config.SERVER_DIR
        if not (server_dir / "server.jar").exists() and not any(
            server_dir.glob("libraries/**/unix_args.txt")
        ):
            raise RuntimeError("No server installed yet. Install a modpack first.")
        self._write_eula(settings.eula_accepted, server_dir)
        if not settings.eula_accepted:
            raise RuntimeError("You must accept the Minecraft EULA before starting.")
        if settings.use_rcon:
            self._configure_rcon(settings)

        self._settings = settings
        cmd = loaders.build_start_command(
            settings.installed_loader, settings.memory_mb,
            settings.extra_jvm_args, server_dir,
        )
        self._append(f"[panel] Starting: {' '.join(cmd)}")
        self._status = "starting"
        self._want_running = True
        self._started_at = time.time()
        self._proc = subprocess.Popen(
            cmd, cwd=str(server_dir),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        self._emit("start", "🟢 Server starting")
        self._reader = threading.Thread(
            target=self._pump_output, args=(settings,), daemon=True
        )
        self._reader.start()

    def stop(self, timeout: float = 30.0) -> None:
        self._want_running = False
        if not self.is_running():
            self._status = "stopped"
            return
        self._append("[panel] Stopping server...")
        try:
            self.send_command("stop")
        except Exception:
            pass
        assert self._proc is not None
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._status = "stopped"

    def restart(self, settings: config.Settings) -> None:
        self.stop()
        time.sleep(1)
        self.start(settings)

    def send_command(self, command: str) -> None:
        if not self.is_running() or self._proc is None or self._proc.stdin is None:
            raise RuntimeError("Server is not running.")
        self._proc.stdin.write(command.rstrip("\n") + "\n")
        self._proc.stdin.flush()
        self._append(f"> {command}")

    def query(self, command: str, timeout: float = 2.0) -> str:
        """Run a command and return its output, preferring RCON over stdin
        so stat polling stays out of the visible console."""
        s = self._settings
        if s and s.use_rcon and self.is_running():
            try:
                return rcon.command("127.0.0.1", s.rcon_port, s.rcon_password, command)
            except Exception:
                pass
        return "\n".join(self.run_and_capture(command, timeout=timeout))

    def run_and_capture(self, command: str, timeout: float = 2.0) -> list[str]:
        """Send a command and return console lines that appeared afterwards."""
        with self._lock:
            start = len(self._console)
        self.send_command(command)
        time.sleep(timeout)
        with self._lock:
            return list(self._console)[start:]

    # -- internals ----------------------------------------------------------
    def _pump_output(self, settings: config.Settings) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for line in self._proc.stdout:
            self._append(line.rstrip("\n"))
            if self._status == "starting" and "Done (" in line:
                self._status = "running"
                self._emit("ready", "✅ Server is ready")
            m = _JOIN_LEAVE.search(line)
            if m:
                who, action = m.group(1), m.group(2)
                if action == "joined":
                    self._emit("join", f"➡️ {who} joined")
                else:
                    self._emit("leave", f"⬅️ {who} left")
        code = self._proc.wait()
        if self._want_running:
            self._status = "crashed"
            self._append(f"[panel] Server exited unexpectedly (code {code}).")
            self._emit("crash", f"🔴 Server crashed (exit {code})")
            if settings.auto_restart:
                self._append("[panel] Auto-restart in 5s...")
                time.sleep(5)
                if self._want_running:
                    self.start(settings)
        else:
            self._status = "stopped"
            self._append(f"[panel] Server stopped (code {code}).")
            self._emit("stop", "⏹️ Server stopped")

    def _emit(self, event_type: str, message: str) -> None:
        if self.on_event:
            try:
                self.on_event(event_type, message)
            except Exception:
                pass

    def _configure_rcon(self, settings: config.Settings) -> None:
        set_property("enable-rcon", "true")
        set_property("rcon.port", str(settings.rcon_port))
        set_property("rcon.password", settings.rcon_password)

    def _append(self, line: str) -> None:
        with self._lock:
            self._console.append(line)

    @staticmethod
    def _write_eula(accepted: bool, server_dir: Path) -> None:
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "eula.txt").write_text(
            f"eula={'true' if accepted else 'false'}\n"
        )


# ---- server.properties helpers -------------------------------------------
def read_properties() -> str:
    path = config.SERVER_DIR / "server.properties"
    return path.read_text() if path.exists() else ""


def write_properties(text: str) -> None:
    config.SERVER_DIR.mkdir(parents=True, exist_ok=True)
    (config.SERVER_DIR / "server.properties").write_text(text)


def set_property(key: str, value: str) -> None:
    """Upsert a single key in server.properties (used to sync the port)."""
    path = config.SERVER_DIR / "server.properties"
    lines = path.read_text().splitlines() if path.exists() else []
    out, found = [], False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")


# Single shared instance used by the web app.
manager = ServerManager()
