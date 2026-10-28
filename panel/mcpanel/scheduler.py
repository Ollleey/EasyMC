"""Scheduled daily restart with in-game warnings.

A background thread checks the clock each minute. At ``restart_time`` minus
``restart_warn_minutes`` it starts warning players in chat, then restarts the
server at the configured time. Uses the container's local time.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

from .server_manager import manager


class RestartScheduler(threading.Thread):
    def __init__(self, get_settings) -> None:
        super().__init__(daemon=True)
        self._get_settings = get_settings
        self._stop = threading.Event()
        self._last_fired = ""   # "YYYY-MM-DD HH:MM" to avoid double-firing
        self._warned_for = ""
        self._cmd_fired: set[str] = set()   # keys of commands fired today
        self._cmd_date = ""                 # date the fired set belongs to

    def run(self) -> None:
        while not self._stop.wait(20):
            try:
                self._tick()
            except Exception:
                pass

    def _tick(self) -> None:
        s = self._get_settings()
        if not manager.is_running():
            return
        self._run_scheduled_commands(s)
        if not s.restart_enabled:
            return
        now = datetime.now()
        target_h, target_m = self._parse(s.restart_time)
        if target_h is None:
            return

        # Minutes until today's target time.
        target_total = target_h * 60 + target_m
        now_total = now.hour * 60 + now.minute
        delta = target_total - now_total
        key = now.strftime("%Y-%m-%d") + f" {target_h:02d}:{target_m:02d}"

        # Warning window.
        if 0 < delta <= s.restart_warn_minutes and self._warned_for != f"{key}:{delta}":
            self._warned_for = f"{key}:{delta}"
            try:
                manager.send_command(f"say Scheduled restart in {delta} minute(s).")
            except Exception:
                pass

        # Fire at the target minute, once.
        if delta == 0 and self._last_fired != key:
            self._last_fired = key
            try:
                manager.send_command("say Restarting now...")
                time.sleep(2)
            except Exception:
                pass
            manager.restart(s)

    def _run_scheduled_commands(self, s) -> None:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        hhmm = now.strftime("%H:%M")
        if today != self._cmd_date:        # new day -> allow all to fire again
            self._cmd_date = today
            self._cmd_fired.clear()
        for i, entry in enumerate(s.scheduled_commands or []):
            if entry.get("time") != hhmm:
                continue
            key = f"{hhmm}#{i}"
            if key in self._cmd_fired:
                continue
            self._cmd_fired.add(key)
            try:
                manager.send_command(entry["command"])
            except Exception:
                pass

    @staticmethod
    def _parse(hhmm: str) -> tuple[int | None, int | None]:
        try:
            h, m = hhmm.strip().split(":")
            return int(h), int(m)
        except (ValueError, AttributeError):
            return None, None

    def stop(self) -> None:
        self._stop.set()
