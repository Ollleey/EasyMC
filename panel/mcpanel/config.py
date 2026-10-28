"""Panel configuration: load and persist settings as JSON.

All paths are resolved relative to the data directory so the whole state
(config, server files, uploaded modpacks) lives under one tree that is easy
to back up.
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, asdict, field
from pathlib import Path
from threading import Lock

# Base data directory. The install script sets MCPANEL_DATA; default suits a
# local dev run.
DATA_DIR = Path(os.environ.get("MCPANEL_DATA", str(Path.home() / "mc-modpack-data")))
CONFIG_FILE = DATA_DIR / "config.json"
SERVER_DIR = DATA_DIR / "server"          # the running Minecraft server lives here
UPLOAD_DIR = DATA_DIR / "uploads"         # raw .mrpack / CurseForge zips land here
BACKUP_DIR = DATA_DIR / "backups"
# User-added mods kept outside the server dir so a modpack reinstall never
# wipes them; they are re-copied into server/mods after every install.
EXTRA_MODS_DIR = DATA_DIR / "extra-mods"

_lock = Lock()


@dataclass
class Settings:
    """Everything the user can tweak from the web panel."""

    # --- JVM / server ---
    memory_mb: int = 4096                 # -Xmx; -Xms is set to the same value
    server_port: int = 25565
    extra_jvm_args: str = "-XX:+UseG1GC -XX:+ParallelRefProcEnabled"
    auto_restart: bool = True             # restart the server if it crashes
    eula_accepted: bool = False           # must be true before first start

    # --- panel ---
    panel_host: str = "0.0.0.0"           # bind all interfaces so Tailscale reaches it
    panel_port: int = 8080
    panel_password: str = ""              # empty on first run -> set during setup
    session_secret: str = field(default_factory=lambda: secrets.token_hex(32))
    setup_done: bool = False              # first-run wizard completed

    # --- backups ---
    backup_enabled: bool = True           # run automatic backups
    backup_interval_hours: int = 12       # how often auto-backups run
    backup_keep: int = 7                  # how many backups to retain

    # --- live map ---
    map_enabled: bool = False             # show the embedded live map
    map_port: int = 8100                  # BlueMap 8100, Dynmap 8123

    # --- scheduled restart ---
    restart_enabled: bool = False
    restart_time: str = "04:00"           # HH:MM, container local time
    restart_warn_minutes: int = 5         # warn players this long before

    # --- scheduled commands --- list of {"time": "HH:MM", "command": "..."}
    scheduled_commands: list = field(default_factory=list)

    # --- discord notifications ---
    discord_enabled: bool = False
    discord_webhook_url: str = ""         # Discord channel webhook URL

    # --- rcon (used for clean stat/command queries) ---
    use_rcon: bool = True
    rcon_port: int = 25575
    rcon_password: str = field(default_factory=lambda: secrets.token_hex(12))

    # --- integrations ---
    curseforge_api_key: str = ""          # required for CurseForge modpacks

    # --- bookkeeping (set by the installer, shown in the UI) ---
    installed_pack_name: str = ""
    installed_loader: str = ""            # fabric | forge | neoforge | quilt | vanilla
    minecraft_version: str = ""
    loader_version: str = ""

    def public_dict(self) -> dict:
        """Settings safe to send to the browser (secrets masked)."""
        data = asdict(self)
        data["panel_password"] = "" if not self.panel_password else "********"
        data["session_secret"] = ""
        data["curseforge_api_key"] = (
            "" if not self.curseforge_api_key else "********"
        )
        data["rcon_password"] = ""
        data["discord_webhook_url"] = (
            "" if not self.discord_webhook_url else "set ✓"
        )
        return data


def _ensure_dirs() -> None:
    for d in (DATA_DIR, SERVER_DIR, UPLOAD_DIR, BACKUP_DIR, EXTRA_MODS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load() -> Settings:
    _ensure_dirs()
    if not CONFIG_FILE.exists():
        s = Settings()
        save(s)
        return s
    raw = json.loads(CONFIG_FILE.read_text())
    known = {f: raw[f] for f in Settings.__dataclass_fields__ if f in raw}
    return Settings(**known)


def save(settings: Settings) -> None:
    _ensure_dirs()
    with _lock:
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(settings), indent=2))
        tmp.replace(CONFIG_FILE)
