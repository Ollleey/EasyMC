"""Safe browsing/editing of text config files inside the server directory.

Only text-like config files are exposed, and every path is confined to the
server dir so the browser can't escape via ``..`` or absolute paths.
"""
from __future__ import annotations

from pathlib import Path

from . import config

_TEXT_SUFFIXES = {".properties", ".toml", ".json", ".json5", ".cfg", ".conf",
                  ".yml", ".yaml", ".txt", ".ini", ".snbt", ".mcmeta"}
_MAX_EDIT_BYTES = 2 * 1024 * 1024  # don't open huge files in the browser


def _root() -> Path:
    return config.SERVER_DIR.resolve()


def safe_path(rel: str) -> Path:
    """Resolve ``rel`` under the server dir, rejecting traversal."""
    root = _root()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Path outside server directory.")
    return target


def list_editable() -> list[str]:
    """Relative paths of editable config files (config tree + top-level)."""
    root = _root()
    found: list[str] = []
    # Top-level config files.
    for p in sorted(root.glob("*")):
        if p.is_file() and p.suffix in _TEXT_SUFFIXES:
            found.append(p.name)
    # The config/ tree (where most mods keep settings).
    cfg = root / "config"
    if cfg.exists():
        for p in sorted(cfg.rglob("*")):
            if p.is_file() and p.suffix in _TEXT_SUFFIXES:
                found.append(str(p.relative_to(root)))
    return found[:500]


def read_file(rel: str) -> str:
    path = safe_path(rel)
    if not path.is_file():
        raise ValueError("Not a file.")
    if path.stat().st_size > _MAX_EDIT_BYTES:
        raise ValueError("File too large to edit here.")
    return path.read_text(errors="replace")


def list_crash_reports() -> list[dict]:
    """Crash reports plus the current log, newest first."""
    root = _root()
    out: list[dict] = []
    cr = root / "crash-reports"
    if cr.exists():
        for p in sorted(cr.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
            out.append({"name": f"crash-reports/{p.name}",
                        "size_kb": p.stat().st_size // 1024})
    latest = root / "logs" / "latest.log"
    if latest.exists():
        out.insert(0, {"name": "logs/latest.log",
                       "size_kb": latest.stat().st_size // 1024})
    return out


def read_log(rel: str) -> str:
    """Read a crash report or log (tail of large files)."""
    path = safe_path(rel)
    if not path.is_file():
        raise ValueError("Not a file.")
    data = path.read_text(errors="replace")
    if len(data) > _MAX_EDIT_BYTES:          # show the tail of huge logs
        data = "... (truncated) ...\n" + data[-_MAX_EDIT_BYTES:]
    return data


def write_file(rel: str, text: str) -> None:
    path = safe_path(rel)
    if path.suffix not in _TEXT_SUFFIXES:
        raise ValueError("Only config/text files can be edited.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
