"""Player management: whitelist, operators, bans and the online list.

Two modes:

* **Server running** -> changes go through the server console (``whitelist
  add``, ``op``, ``ban`` ...). This is authoritative and resolves UUIDs
  itself.
* **Server stopped** -> whitelist add/remove edits ``whitelist.json``
  directly, resolving the UUID via the Mojang API so the entry is valid on
  next start. Ops/bans require a running server.

The display always reads the JSON files the server maintains.
"""
from __future__ import annotations

import json
import re
import uuid as uuidlib
from pathlib import Path

import httpx

from . import config
from .server_manager import manager

MOJANG_PROFILE = "https://api.mojang.com/users/profiles/minecraft/{name}"
_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def _read_json_list(filename: str) -> list[dict]:
    path = config.SERVER_DIR / filename
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text() or "[]")
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def _write_json_list(filename: str, data: list[dict]) -> None:
    config.SERVER_DIR.mkdir(parents=True, exist_ok=True)
    (config.SERVER_DIR / filename).write_text(json.dumps(data, indent=2))


def validate_name(name: str) -> str:
    name = name.strip()
    if not _NAME_RE.match(name):
        raise ValueError("Invalid Minecraft name.")
    return name


def lookup_uuid(name: str) -> tuple[str, str]:
    """Return (dashed-uuid, canonical-name) from Mojang. Raises on failure."""
    r = httpx.get(MOJANG_PROFILE.format(name=name), timeout=15.0)
    if r.status_code != 200 or not r.content:
        raise RuntimeError(f"Player '{name}' not found on Mojang.")
    data = r.json()
    raw = data["id"]
    dashed = str(uuidlib.UUID(raw))
    return dashed, data["name"]


def whitelist_enabled() -> bool:
    props = config.SERVER_DIR / "server.properties"
    if not props.exists():
        return False
    for line in props.read_text().splitlines():
        if line.startswith("white-list="):
            return line.split("=", 1)[1].strip().lower() == "true"
    return False


def snapshot() -> dict:
    """Everything the Players panel needs."""
    return {
        "whitelist_enabled": whitelist_enabled(),
        "whitelist": [p.get("name", "?") for p in _read_json_list("whitelist.json")],
        "ops": [p.get("name", "?") for p in _read_json_list("ops.json")],
        "banned": [p.get("name", "?") for p in _read_json_list("banned-players.json")],
        "server_running": manager.is_running(),
    }


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def set_whitelist(enabled: bool) -> None:
    from .server_manager import set_property
    set_property("white-list", "true" if enabled else "false")
    if manager.is_running():
        manager.send_command("whitelist on" if enabled else "whitelist off")


def whitelist_add(name: str) -> None:
    name = validate_name(name)
    if manager.is_running():
        manager.send_command(f"whitelist add {name}")
        return
    # Offline: resolve UUID and edit the file.
    dashed, canon = lookup_uuid(name)
    entries = _read_json_list("whitelist.json")
    if not any(e.get("uuid") == dashed for e in entries):
        entries.append({"uuid": dashed, "name": canon})
        _write_json_list("whitelist.json", entries)


def whitelist_remove(name: str) -> None:
    name = validate_name(name)
    if manager.is_running():
        manager.send_command(f"whitelist remove {name}")
        return
    entries = [e for e in _read_json_list("whitelist.json")
               if e.get("name", "").lower() != name.lower()]
    _write_json_list("whitelist.json", entries)


def _require_running(action: str) -> None:
    if not manager.is_running():
        raise RuntimeError(f"Start the server to {action}.")


def op_add(name: str) -> None:
    _require_running("add an operator")
    manager.send_command(f"op {validate_name(name)}")


def op_remove(name: str) -> None:
    _require_running("remove an operator")
    manager.send_command(f"deop {validate_name(name)}")


def ban(name: str) -> None:
    _require_running("ban a player")
    manager.send_command(f"ban {validate_name(name)}")


def unban(name: str) -> None:
    _require_running("unban a player")
    manager.send_command(f"pardon {validate_name(name)}")


def online_players() -> str:
    """Ask the running server who is online and return the parsed summary."""
    if not manager.is_running():
        return "Server not running."
    out = manager.query("list", timeout=1.5)
    for line in reversed(out.splitlines()):
        if "players online" in line:
            # Strip any log prefix "[HH:MM:SS] [Server thread/INFO]: "
            return re.sub(r"^.*?\]:?\s*", "", line).strip() or line.strip()
    return out.strip() or "No response (try again)."
