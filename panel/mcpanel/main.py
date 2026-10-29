"""FastAPI web panel: login, dashboard, modpack install, settings, console.

The panel binds to 0.0.0.0 by default so it is reachable over a Tailscale
address without extra proxying. A single password gates everything; there
are no user accounts.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import backups, config, files, modpacks, notify, players, playtime, scheduler, updater
from .tunnel import tunnel
from .server_manager import manager, read_properties, write_properties, set_property

BASE = Path(__file__).parent
app = FastAPI(title="MC Modpack Panel")
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

_settings = config.load()
app.add_middleware(SessionMiddleware, secret_key=_settings.session_secret)

# Auto-backup runs in the background using the live settings object.
_autobackup = backups.AutoBackup(lambda: _settings)
_autobackup.start()

# Scheduled daily restart.
_restart_scheduler = scheduler.RestartScheduler(lambda: _settings)
_restart_scheduler.start()


# Server/player events: Discord notifications + playtime tracking.
def _on_event(event_type: str, message: str) -> None:
    if _settings.discord_enabled and _settings.discord_webhook_url:
        notify.send(_settings.discord_webhook_url, message)
    if event_type in ("join", "leave"):
        parts = message.split()
        if len(parts) >= 2:
            name = parts[1]
            (playtime.record_join if event_type == "join" else playtime.record_leave)(name)


manager.on_event = _on_event

# ---- background install job state ----------------------------------------
_job_lock = threading.Lock()
_job = {"running": False, "log": [], "done": False, "ok": False}


def _job_push(msg: str) -> None:
    with _job_lock:
        _job["log"].append(msg)


def _reset_job() -> None:
    with _job_lock:
        _job.update(running=True, log=[], done=False, ok=False)


# ---- auth helpers ---------------------------------------------------------
_PBKDF2_ITERS = 200_000


def _hash_pw(password: str, salt: str | None = None) -> str:
    """Salted PBKDF2-HMAC-SHA256, stored as ``pbkdf2$iters$salt$hash``."""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERS)
    return f"pbkdf2${_PBKDF2_ITERS}${salt}${dk.hex()}"


def _verify_pw(password: str, stored: str) -> tuple[bool, str | None]:
    """Return (ok, upgraded_hash). upgraded_hash is set when a legacy
    unsalted SHA-256 password verified and should be re-stored as PBKDF2."""
    if not stored:
        return False, None
    if stored.startswith("pbkdf2$"):
        try:
            _, iters, salt, h = stored.split("$")
            dk = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(salt), int(iters)
            )
            return hmac.compare_digest(dk.hex(), h), None
        except (ValueError, TypeError):
            return False, None
    # Legacy: unsalted SHA-256 hex -> verify and upgrade on success.
    legacy = hashlib.sha256(password.encode()).hexdigest()
    if hmac.compare_digest(stored, legacy):
        return True, _hash_pw(password)
    return False, None


# Simple per-IP login throttle to blunt brute-force attempts.
_login_fails: dict[str, list[float]] = {}
_LOCK_THRESHOLD = 5       # failures within the window before locking
_LOCK_WINDOW = 300.0      # seconds a failure is remembered
_LOCK_TIME = 60.0         # seconds locked out once the threshold is hit


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_locked(ip: str) -> float:
    """Seconds of lockout remaining for this IP (0 if not locked)."""
    now = time.time()
    fails = [t for t in _login_fails.get(ip, []) if now - t < _LOCK_WINDOW]
    _login_fails[ip] = fails
    if len(fails) >= _LOCK_THRESHOLD:
        return max(0.0, fails[-1] + _LOCK_TIME - now)
    return 0.0


def _authed(request: Request) -> bool:
    return bool(request.session.get("auth"))


def _require(request: Request) -> None:
    if not _authed(request):
        raise HTTPException(status_code=401, detail="Login required")


# ==========================================================================
# Auth
# ==========================================================================
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    needs_setup = not _settings.panel_password
    return templates.TemplateResponse(
        "login.html", {"request": request, "needs_setup": needs_setup}
    )


@app.post("/login")
def login(request: Request, password: str = Form(...)):
    ip = _client_ip(request)
    locked = _login_locked(ip)
    if locked > 0:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "needs_setup": False,
             "error": f"Too many attempts. Try again in {int(locked) + 1}s."},
            status_code=429,
        )

    if not _settings.panel_password:
        # First run: the typed password becomes the panel password.
        _settings.panel_password = _hash_pw(password)
        config.save(_settings)

    ok, upgraded = _verify_pw(password, _settings.panel_password)
    if ok:
        if upgraded:                       # migrate a legacy hash in place
            _settings.panel_password = upgraded
            config.save(_settings)
        _login_fails.pop(ip, None)
        request.session["auth"] = secrets.token_hex(8)
        return RedirectResponse("/", status_code=303)

    _login_fails.setdefault(ip, []).append(time.time())
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "needs_setup": False, "error": "Wrong password."},
        status_code=401,
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ==========================================================================
# Dashboard
# ==========================================================================
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=303)
    if not _settings.setup_done:
        return RedirectResponse("/setup", status_code=303)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "settings": _settings.public_dict(),
            "status": manager.status,
        },
    )


# ==========================================================================
# First-run setup wizard
# ==========================================================================
@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        "setup.html", {"request": request, "settings": _settings.public_dict()}
    )


@app.post("/setup")
def setup_save(
    request: Request,
    memory_mb: int = Form(4096),
    server_port: int = Form(25565),
    eula_accepted: bool = Form(False),
    backup_enabled: bool = Form(False),
    use_rcon: bool = Form(False),
    map_enabled: bool = Form(False),
    discord_enabled: bool = Form(False),
    discord_webhook_url: str = Form(""),
    restart_enabled: bool = Form(False),
    curseforge_api_key: str = Form(""),
):
    if not _authed(request):
        return RedirectResponse("/login", status_code=303)
    _settings.memory_mb = max(512, memory_mb)
    _settings.server_port = server_port
    _settings.eula_accepted = eula_accepted
    _settings.backup_enabled = backup_enabled
    _settings.use_rcon = use_rcon
    _settings.map_enabled = map_enabled
    _settings.discord_enabled = discord_enabled
    if discord_webhook_url.strip():
        _settings.discord_webhook_url = discord_webhook_url.strip()
    _settings.restart_enabled = restart_enabled
    if curseforge_api_key.strip():
        _settings.curseforge_api_key = curseforge_api_key.strip()
    _settings.setup_done = True
    config.save(_settings)
    return RedirectResponse("/", status_code=303)


@app.get("/api/status")
def api_status(request: Request):
    _require(request)
    with _job_lock:
        job = dict(_job)
    return {
        "server_status": manager.status,
        "console": manager.console_text(),
        "pack": _settings.installed_pack_name,
        "loader": _settings.installed_loader,
        "mc_version": _settings.minecraft_version,
        "map_enabled": _settings.map_enabled,
        "map_port": _settings.map_port,
        "job": job,
    }


# ==========================================================================
# Server control
# ==========================================================================
@app.post("/api/server/{action}")
def server_control(request: Request, action: str):
    _require(request)
    try:
        if action == "start":
            set_property("server-port", str(_settings.server_port))
            manager.start(_settings)
        elif action == "stop":
            manager.stop()
        elif action == "restart":
            manager.restart(_settings)
        else:
            raise HTTPException(400, "Unknown action")
    except Exception as exc:  # surface the reason to the UI
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "status": manager.status}


@app.post("/api/command")
def send_command(request: Request, command: str = Form(...)):
    _require(request)
    try:
        manager.send_command(command)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True}


# ==========================================================================
# Modpack installation
# ==========================================================================
def _run_install(kind: str, *, link: str = "", upload_path: Path | None = None) -> None:
    """Background worker. ``kind`` is modrinth|curseforge."""
    try:
        if manager.is_running():
            _job_push("Stopping running server before install...")
            manager.stop()

        if kind == "modrinth":
            pack_file = config.UPLOAD_DIR / "resolved.mrpack"
            if link:
                _job_push(f"Resolving Modrinth: {link}")
                modpacks.resolve_modrinth(link, pack_file)
            else:
                pack_file = upload_path  # already an .mrpack
            _job_push("Installing Modrinth pack (loader + mods)...")
            result = modpacks.install_mrpack(pack_file, config.SERVER_DIR)
        elif kind == "curseforge":
            pack_file = config.UPLOAD_DIR / "resolved.zip"
            if link:
                _job_push(f"Resolving CurseForge: {link}")
                modpacks.resolve_curseforge(
                    link, _settings.curseforge_api_key, pack_file
                )
            else:
                pack_file = upload_path
            _job_push("Installing CurseForge pack (loader + mods)...")
            result = modpacks.install_curseforge_zip(
                pack_file, _settings.curseforge_api_key, config.SERVER_DIR
            )
        else:
            raise RuntimeError(f"Unknown source: {kind}")

        extra = modpacks.apply_extra_mods(config.SERVER_DIR)
        if extra:
            _job_push(f"Re-applied {extra} custom mod(s) from extra-mods.")

        _settings.installed_pack_name = result.pack_name
        _settings.installed_loader = result.loader
        _settings.minecraft_version = result.minecraft_version
        _settings.loader_version = result.loader_version
        config.save(_settings)

        _job_push(
            f"Done: {result.pack_name} ({result.loader} {result.minecraft_version}), "
            f"{result.files_installed} files."
        )
        for w in result.warnings:
            _job_push(f"WARN: {w}")
        with _job_lock:
            _job.update(ok=True)
    except Exception as exc:
        _job_push(f"ERROR: {exc}")
    finally:
        with _job_lock:
            _job.update(running=False, done=True)


@app.post("/api/install/link")
def install_from_link(
    request: Request, source: str = Form(...), link: str = Form(...)
):
    _require(request)
    with _job_lock:
        if _job["running"]:
            return JSONResponse({"ok": False, "error": "Install already running"}, 409)
    _reset_job()
    threading.Thread(
        target=_run_install, args=(source,), kwargs={"link": link.strip()}, daemon=True
    ).start()
    return {"ok": True}


@app.post("/api/install/upload")
async def install_from_upload(
    request: Request, source: str = Form(...), file: UploadFile = File(...)
):
    _require(request)
    with _job_lock:
        if _job["running"]:
            return JSONResponse({"ok": False, "error": "Install already running"}, 409)
    suffix = ".mrpack" if source == "modrinth" else ".zip"
    dest = config.UPLOAD_DIR / f"upload{suffix}"
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        while chunk := await file.read(1 << 20):
            fh.write(chunk)
    _reset_job()
    threading.Thread(
        target=_run_install, args=(source,), kwargs={"upload_path": dest}, daemon=True
    ).start()
    return {"ok": True}


# ==========================================================================
# Settings + server.properties
# ==========================================================================
@app.post("/api/settings")
def update_settings(
    request: Request,
    memory_mb: int = Form(...),
    server_port: int = Form(...),
    extra_jvm_args: str = Form(""),
    auto_restart: bool = Form(False),
    eula_accepted: bool = Form(False),
    curseforge_api_key: str = Form(""),
    new_password: str = Form(""),
    backup_enabled: bool = Form(False),
    backup_interval_hours: int = Form(12),
    backup_keep: int = Form(7),
    map_enabled: bool = Form(False),
    map_port: int = Form(8100),
    restart_enabled: bool = Form(False),
    restart_time: str = Form("04:00"),
    restart_warn_minutes: int = Form(5),
    discord_enabled: bool = Form(False),
    discord_webhook_url: str = Form(""),
    use_rcon: bool = Form(False),
):
    _require(request)
    _settings.memory_mb = max(512, memory_mb)
    _settings.server_port = server_port
    _settings.extra_jvm_args = extra_jvm_args
    _settings.auto_restart = auto_restart
    _settings.eula_accepted = eula_accepted
    _settings.backup_enabled = backup_enabled
    _settings.backup_interval_hours = max(1, backup_interval_hours)
    _settings.backup_keep = max(1, backup_keep)
    _settings.map_enabled = map_enabled
    _settings.map_port = map_port
    _settings.restart_enabled = restart_enabled
    _settings.restart_time = restart_time
    _settings.restart_warn_minutes = max(0, restart_warn_minutes)
    _settings.discord_enabled = discord_enabled
    if discord_webhook_url and discord_webhook_url != "set ✓":
        _settings.discord_webhook_url = discord_webhook_url.strip()
    _settings.use_rcon = use_rcon
    if curseforge_api_key and curseforge_api_key != "********":
        _settings.curseforge_api_key = curseforge_api_key.strip()
    if new_password:
        _settings.panel_password = _hash_pw(new_password)
    config.save(_settings)
    return {"ok": True}


# ==========================================================================
# Extra mods (persistent, survive modpack reinstalls)
# ==========================================================================
@app.get("/api/mods")
def list_mods(request: Request):
    _require(request)
    config.EXTRA_MODS_DIR.mkdir(parents=True, exist_ok=True)
    extra = sorted(p.name for p in config.EXTRA_MODS_DIR.glob("*.jar"))
    server_mods = config.SERVER_DIR / "mods"
    active = {p.name for p in server_mods.glob("*.jar")} if server_mods.exists() else set()
    return {
        "extra_mods": [{"name": n, "active": n in active} for n in extra],
    }


@app.post("/api/mods/upload")
async def upload_mod(request: Request, file: UploadFile = File(...)):
    _require(request)
    name = Path(file.filename or "").name
    if not name.endswith(".jar"):
        return JSONResponse({"ok": False, "error": "Only .jar files"}, status_code=400)
    config.EXTRA_MODS_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.EXTRA_MODS_DIR / name
    with dest.open("wb") as fh:
        while chunk := await file.read(1 << 20):
            fh.write(chunk)
    # Make it live right away if a server is already installed.
    applied = modpacks.apply_extra_mods(config.SERVER_DIR)
    return {"ok": True, "name": name, "applied": applied}


@app.post("/api/mods/delete")
def delete_mod(request: Request, name: str = Form(...)):
    _require(request)
    safe = Path(name).name
    (config.EXTRA_MODS_DIR / safe).unlink(missing_ok=True)
    # Also remove the copy from the live server dir.
    (config.SERVER_DIR / "mods" / safe).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/properties", response_class=JSONResponse)
def get_properties(request: Request):
    _require(request)
    return {"text": read_properties()}


@app.post("/api/properties")
def post_properties(request: Request, text: str = Form(...)):
    _require(request)
    write_properties(text)
    return {"ok": True}


# ==========================================================================
# Backups
# ==========================================================================
@app.get("/api/backups")
def api_backups(request: Request):
    _require(request)
    return {
        "backups": backups.list_backups(),
        "enabled": _settings.backup_enabled,
        "interval_hours": _settings.backup_interval_hours,
        "keep": _settings.backup_keep,
        "state": backups.state(),
    }


@app.post("/api/backups/create")
def api_backup_create(request: Request):
    _require(request)
    try:
        path = backups.create_backup(label="manual")
        backups.prune(_settings.backup_keep)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "name": path.name}


@app.post("/api/backups/delete")
def api_backup_delete(request: Request, name: str = Form(...)):
    _require(request)
    backups.delete_backup(name)
    return {"ok": True}


@app.post("/api/backups/restore")
def api_backup_restore(request: Request, name: str = Form(...)):
    _require(request)
    try:
        was_running = manager.is_running()
        if was_running:
            manager.stop()
        backups.restore_backup(name)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "restarted": False,
            "note": "Backup restored. Start the server when ready."}


# ==========================================================================
# Players: whitelist, ops, bans, online
# ==========================================================================
@app.get("/api/players")
def api_players(request: Request):
    _require(request)
    return players.snapshot()


def _player_action(fn, *args):
    try:
        fn(*args)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True}


@app.post("/api/whitelist/toggle")
def api_whitelist_toggle(request: Request, enabled: bool = Form(...)):
    _require(request)
    return _player_action(players.set_whitelist, enabled)


@app.post("/api/whitelist/add")
def api_whitelist_add(request: Request, name: str = Form(...)):
    _require(request)
    return _player_action(players.whitelist_add, name)


@app.post("/api/whitelist/remove")
def api_whitelist_remove(request: Request, name: str = Form(...)):
    _require(request)
    return _player_action(players.whitelist_remove, name)


@app.post("/api/ops/add")
def api_ops_add(request: Request, name: str = Form(...)):
    _require(request)
    return _player_action(players.op_add, name)


@app.post("/api/ops/remove")
def api_ops_remove(request: Request, name: str = Form(...)):
    _require(request)
    return _player_action(players.op_remove, name)


@app.post("/api/ban")
def api_ban(request: Request, name: str = Form(...)):
    _require(request)
    return _player_action(players.ban, name)


@app.post("/api/unban")
def api_unban(request: Request, name: str = Form(...)):
    _require(request)
    return _player_action(players.unban, name)


@app.get("/api/players/online")
def api_players_online(request: Request):
    _require(request)
    return {"online": players.online_players()}


# ==========================================================================
# Live stats
# ==========================================================================
@app.get("/api/stats")
def api_stats(request: Request):
    _require(request)
    st = manager.stats()
    st["max_mb"] = _settings.memory_mb
    st["status"] = manager.status
    return st


# ==========================================================================
# Mod browser (Modrinth search + add single mod)
# ==========================================================================
@app.post("/api/mods/search")
def api_mods_search(request: Request, q: str = Form("")):
    _require(request)
    try:
        hits = modpacks.search_modrinth_mods(
            q, _settings.minecraft_version, _settings.installed_loader
        )
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "hits": hits}


@app.post("/api/mods/add_modrinth")
def api_mods_add_modrinth(request: Request, project_id: str = Form(...)):
    _require(request)
    try:
        name = modpacks.add_mod_from_modrinth(
            project_id, _settings.minecraft_version, _settings.installed_loader,
            config.EXTRA_MODS_DIR,
        )
        modpacks.apply_extra_mods(config.SERVER_DIR)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "name": name}


# ==========================================================================
# World import
# ==========================================================================
@app.post("/api/world/import")
async def api_world_import(request: Request, file: UploadFile = File(...)):
    _require(request)
    import shutil
    import tempfile
    import zipfile

    if manager.is_running():
        manager.stop()
    tmpzip = config.UPLOAD_DIR / "world-import.zip"
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with tmpzip.open("wb") as fh:
        while chunk := await file.read(1 << 20):
            fh.write(chunk)
    try:
        backups.create_backup(label="pre-import")  # safety net
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            with zipfile.ZipFile(tmpzip) as zf:
                zf.extractall(tdp)
            level = next(tdp.rglob("level.dat"), None)
            if level is None:
                raise RuntimeError("No level.dat found in the zip.")
            world_src = level.parent
            world_dst = config.SERVER_DIR / "world"
            if world_dst.exists():
                shutil.rmtree(world_dst, ignore_errors=True)
            shutil.move(str(world_src), str(world_dst))
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "note": "World imported. Start the server when ready."}


# ==========================================================================
# Server icon
# ==========================================================================
@app.post("/api/icon")
async def api_icon(request: Request, file: UploadFile = File(...)):
    _require(request)
    if not (file.filename or "").lower().endswith(".png"):
        return JSONResponse({"ok": False, "error": "Must be a .png"}, status_code=400)
    config.SERVER_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.SERVER_DIR / "server-icon.png"
    with dest.open("wb") as fh:
        while chunk := await file.read(1 << 20):
            fh.write(chunk)
    return {"ok": True, "note": "Icon saved. Must be 64x64 PNG; restart to apply."}


# ==========================================================================
# Config file browser
# ==========================================================================
@app.get("/api/files")
def api_files(request: Request):
    _require(request)
    return {"files": files.list_editable()}


@app.post("/api/files/read")
def api_files_read(request: Request, path: str = Form(...)):
    _require(request)
    try:
        return {"ok": True, "text": files.read_file(path)}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.post("/api/files/write")
def api_files_write(request: Request, path: str = Form(...), text: str = Form(...)):
    _require(request)
    try:
        files.write_file(path, text)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True}


# ==========================================================================
# Performance preset (Aikar's flags)
# ==========================================================================
def _aikar_flags(memory_mb: int) -> str:
    big = memory_mb >= 12000
    return " ".join([
        "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
        f"-XX:G1NewSizePercent={40 if big else 30}",
        f"-XX:G1MaxNewSizePercent={50 if big else 40}",
        f"-XX:G1HeapRegionSize={'16M' if big else '8M'}",
        f"-XX:G1ReservePercent={15 if big else 20}",
        "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
        f"-XX:InitiatingHeapOccupancyPercent={20 if big else 15}",
        "-XX:G1MixedGCLiveThresholdPercent=90",
        "-XX:G1RSetUpdatingPauseTimePercent=5", "-XX:SurvivorRatio=32",
        "-XX:+PerfDisableSharedMem", "-XX:MaxTenuringThreshold=1",
        "-Dusing.aikars.flags=https://mcflags.emc.gs", "-Daikars.new.flags=true",
    ])


@app.post("/api/performance/aikar")
def api_perf_aikar(request: Request):
    _require(request)
    _settings.extra_jvm_args = _aikar_flags(_settings.memory_mb)
    config.save(_settings)
    return {"ok": True, "flags": _settings.extra_jvm_args}


# ==========================================================================
# World download
# ==========================================================================
@app.get("/api/world/download")
def api_world_download(request: Request):
    _require(request)
    import shutil
    world = config.SERVER_DIR / "world"
    if not world.exists():
        return JSONResponse({"ok": False, "error": "No world to download."}, 404)
    base = config.UPLOAD_DIR / "world-export"
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    archive = shutil.make_archive(str(base), "zip", root_dir=str(config.SERVER_DIR),
                                  base_dir="world")
    return FileResponse(archive, filename="world.zip", media_type="application/zip")


# ==========================================================================
# Scheduled commands
# ==========================================================================
@app.get("/api/schedule")
def api_schedule(request: Request):
    _require(request)
    return {"commands": _settings.scheduled_commands}


@app.post("/api/schedule/add")
def api_schedule_add(request: Request, time: str = Form(...), command: str = Form(...)):
    _require(request)
    import re as _re
    m = _re.match(r"^(\d{1,2}):(\d{2})$", time.strip())
    if not m or not (0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59):
        return JSONResponse({"ok": False, "error": "Time must be HH:MM (00:00–23:59)"}, 400)
    time = f"{int(m.group(1)):02d}:{m.group(2)}"   # normalise e.g. 4:30 -> 04:30
    if not command.strip():
        return JSONResponse({"ok": False, "error": "Command is empty"}, 400)
    _settings.scheduled_commands.append(
        {"time": time.strip(), "command": command.strip()}
    )
    config.save(_settings)
    return {"ok": True}


@app.post("/api/schedule/delete")
def api_schedule_delete(request: Request, index: int = Form(...)):
    _require(request)
    if 0 <= index < len(_settings.scheduled_commands):
        _settings.scheduled_commands.pop(index)
        config.save(_settings)
    return {"ok": True}


# ==========================================================================
# playit.gg tunnel
# ==========================================================================
@app.get("/api/tunnel")
def api_tunnel(request: Request):
    _require(request)
    return {"running": tunnel.is_running(), "output": tunnel.output()}


@app.post("/api/tunnel/{action}")
def api_tunnel_control(request: Request, action: str):
    _require(request)
    try:
        if action == "start":
            tunnel.start()
        elif action == "stop":
            tunnel.stop()
        else:
            raise HTTPException(400, "Unknown action")
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "running": tunnel.is_running()}


# ==========================================================================
# BlueMap one-click
# ==========================================================================
@app.post("/api/mods/add_bluemap")
def api_add_bluemap(request: Request):
    _require(request)
    try:
        name = modpacks.add_mod_from_modrinth(
            "bluemap", _settings.minecraft_version, _settings.installed_loader,
            config.EXTRA_MODS_DIR,
        )
        modpacks.apply_extra_mods(config.SERVER_DIR)
        _settings.map_enabled = True
        _settings.map_port = 8100
        config.save(_settings)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "name": name}


# ==========================================================================
# Crash reports & logs
# ==========================================================================
@app.get("/api/crashreports")
def api_crashreports(request: Request):
    _require(request)
    return {"reports": files.list_crash_reports()}


@app.post("/api/crashreports/read")
def api_crashreports_read(request: Request, name: str = Form(...)):
    _require(request)
    try:
        return {"ok": True, "text": files.read_log(name)}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


# ==========================================================================
# Playtime
# ==========================================================================
@app.get("/api/playtime")
def api_playtime(request: Request):
    _require(request)
    return {"players": playtime.snapshot()}


# ==========================================================================
# World pre-generation (Chunky)
# ==========================================================================
@app.post("/api/mods/add_chunky")
def api_add_chunky(request: Request):
    _require(request)
    try:
        name = modpacks.add_mod_from_modrinth(
            "chunky", _settings.minecraft_version, _settings.installed_loader,
            config.EXTRA_MODS_DIR,
        )
        modpacks.apply_extra_mods(config.SERVER_DIR)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "name": name}


@app.post("/api/pregen/start")
def api_pregen_start(request: Request, radius: int = Form(1000)):
    _require(request)
    try:
        manager.send_command(f"chunky radius {max(1, radius)}")
        manager.send_command("chunky start")
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True}


@app.post("/api/pregen/cancel")
def api_pregen_cancel(request: Request):
    _require(request)
    try:
        manager.send_command("chunky cancel")
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True}


# ==========================================================================
# PWA service worker (served at root for full scope)
# ==========================================================================
@app.get("/sw.js")
def service_worker():
    return FileResponse(
        str(BASE / "static" / "sw.js"), media_type="application/javascript"
    )


# ==========================================================================
# Maintenance: world reset, modpack removal, self-update
# ==========================================================================
@app.post("/api/world/reset")
def api_world_reset(request: Request):
    _require(request)
    import shutil
    try:
        if manager.is_running():
            manager.stop()
        backups.create_backup(label="pre-world-reset")
        for w in ("world", "world_nether", "world_the_end"):
            shutil.rmtree(config.SERVER_DIR / w, ignore_errors=True)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "note": "World deleted (backup made). A fresh one generates on Start."}


@app.post("/api/modpack/reset")
def api_modpack_reset(request: Request):
    _require(request)
    try:
        if manager.is_running():
            manager.stop()
        backups.create_backup(label="pre-modpack-reset")
        modpacks._clean_server_dir(config.SERVER_DIR)   # keeps worlds + properties
        _settings.installed_pack_name = ""
        _settings.installed_loader = ""
        _settings.minecraft_version = ""
        _settings.loader_version = ""
        config.save(_settings)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "note": "Modpack removed, world kept. Install a new pack."}


@app.get("/api/update/check")
def api_update_check(request: Request):
    _require(request)
    return updater.check()


@app.post("/api/update/apply")
def api_update_apply(request: Request):
    _require(request)
    result = updater.apply()
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)


@app.get("/healthz")
def healthz():
    return {"ok": True}
