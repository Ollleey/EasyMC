"""Install the correct mod loader into the server directory and work out
how to start it.

Each loader ships its server differently:

* Fabric / Quilt  -> a small launcher jar that pulls the rest at runtime.
* Forge / NeoForge -> an installer that unpacks libraries and writes an
  args file we pass to the JVM with ``@``.

The public surface is two functions: :func:`install_loader` and
:func:`build_start_command`.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import httpx

FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEOFORGE_MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"
PISTON_MANIFEST = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"

TIMEOUT = httpx.Timeout(60.0, connect=30.0)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=TIMEOUT, follow_redirects=True) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)


def _run_java(args: list[str], cwd: Path) -> None:
    """Run a java command, raising with captured output on failure."""
    proc = subprocess.run(
        ["java", *args], cwd=str(cwd), capture_output=True, text=True
    )
    if proc.returncode != 0:
        tail = (proc.stdout[-2000:] + proc.stderr[-2000:]).strip()
        raise RuntimeError(f"java {' '.join(args)} failed:\n{tail}")


# --------------------------------------------------------------------------
# Vanilla server jar (needed by Fabric/Quilt and as a fallback)
# --------------------------------------------------------------------------
def download_vanilla_server(mc_version: str, server_dir: Path) -> Path:
    manifest = httpx.get(PISTON_MANIFEST, timeout=TIMEOUT).json()
    entry = next((v for v in manifest["versions"] if v["id"] == mc_version), None)
    if entry is None:
        raise RuntimeError(f"Unknown Minecraft version: {mc_version}")
    meta = httpx.get(entry["url"], timeout=TIMEOUT).json()
    url = meta["downloads"]["server"]["url"]
    dest = server_dir / "server.jar"
    _download(url, dest)
    return dest


# --------------------------------------------------------------------------
# Fabric
# --------------------------------------------------------------------------
def install_fabric(mc_version: str, loader_version: str, server_dir: Path) -> None:
    if not loader_version:
        loaders = httpx.get(
            f"{FABRIC_META}/versions/loader/{mc_version}", timeout=TIMEOUT
        ).json()
        loader_version = loaders[0]["loader"]["version"]
    installers = httpx.get(f"{FABRIC_META}/versions/installer", timeout=TIMEOUT).json()
    installer_version = installers[0]["version"]
    url = (
        f"{FABRIC_META}/versions/loader/{mc_version}/{loader_version}"
        f"/{installer_version}/server/jar"
    )
    _download(url, server_dir / "server.jar")


# --------------------------------------------------------------------------
# Quilt (best-effort: uses the installer jar)
# --------------------------------------------------------------------------
def install_quilt(mc_version: str, loader_version: str, server_dir: Path) -> None:
    meta = httpx.get(f"{QUILT_META}/versions/installer", timeout=TIMEOUT).json()
    installer_url = meta[0]["url"]
    installer = server_dir / "quilt-installer.jar"
    _download(installer_url, installer)
    args = ["-jar", installer.name, "install", "server", mc_version]
    if loader_version:
        args.append(loader_version)
    args += ["--install-dir=.", "--download-server"]
    _run_java(args, server_dir)
    installer.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Forge / NeoForge (installer writes libraries + a unix_args file)
# --------------------------------------------------------------------------
def install_forge(mc_version: str, loader_version: str, server_dir: Path) -> None:
    full = f"{mc_version}-{loader_version}"
    url = f"{FORGE_MAVEN}/{full}/forge-{full}-installer.jar"
    installer = server_dir / "forge-installer.jar"
    _download(url, installer)
    _run_java(["-jar", installer.name, "--installServer"], server_dir)
    installer.unlink(missing_ok=True)
    (server_dir / "forge-installer.jar.log").unlink(missing_ok=True)


def install_neoforge(mc_version: str, loader_version: str, server_dir: Path) -> None:
    url = f"{NEOFORGE_MAVEN}/{loader_version}/neoforge-{loader_version}-installer.jar"
    installer = server_dir / "neoforge-installer.jar"
    _download(url, installer)
    _run_java(["-jar", installer.name, "--installServer"], server_dir)
    installer.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------
def install_loader(
    loader: str, mc_version: str, loader_version: str, server_dir: Path
) -> None:
    loader = (loader or "vanilla").lower()
    server_dir.mkdir(parents=True, exist_ok=True)
    if loader == "vanilla":
        download_vanilla_server(mc_version, server_dir)
    elif loader == "fabric":
        install_fabric(mc_version, loader_version, server_dir)
    elif loader == "quilt":
        install_quilt(mc_version, loader_version, server_dir)
    elif loader == "forge":
        install_forge(mc_version, loader_version, server_dir)
    elif loader == "neoforge":
        install_neoforge(mc_version, loader_version, server_dir)
    else:
        raise RuntimeError(f"Unsupported loader: {loader}")


def _find_unix_args(server_dir: Path) -> Path | None:
    """Forge/NeoForge drop an args file under libraries/.../unix_args.txt."""
    candidates = sorted(server_dir.glob("libraries/**/unix_args.txt"))
    return candidates[0] if candidates else None


def build_start_command(
    loader: str, memory_mb: int, extra_jvm_args: str, server_dir: Path
) -> list[str]:
    """Return the full java argv used to launch the server."""
    loader = (loader or "vanilla").lower()
    xmx = f"-Xmx{memory_mb}M"
    xms = f"-Xms{memory_mb}M"
    extra = [a for a in extra_jvm_args.split() if a]

    if loader in ("forge", "neoforge"):
        args_file = _find_unix_args(server_dir)
        if args_file is not None:
            rel = args_file.relative_to(server_dir)
            return ["java", xmx, xms, *extra, f"@{rel}", "nogui"]
        # Fall through to a plain run.sh style jar if present.
        run_sh = server_dir / "run.sh"
        if run_sh.exists():
            return ["bash", "run.sh", "nogui"]

    # Fabric / Quilt / Vanilla all boot from server.jar.
    return ["java", xmx, xms, *extra, "-jar", "server.jar", "nogui"]


_LOADER_FROM_DEP = {
    "fabric-loader": "fabric",
    "quilt-loader": "quilt",
    "forge": "forge",
    "neoforge": "neoforge",
}


def detect_loader_from_mrpack(dependencies: dict) -> tuple[str, str, str]:
    """Map a Modrinth index ``dependencies`` block to (loader, mc, loader_ver)."""
    mc = dependencies.get("minecraft", "")
    for dep_key, loader in _LOADER_FROM_DEP.items():
        if dep_key in dependencies:
            return loader, mc, dependencies[dep_key]
    return "vanilla", mc, ""


def parse_curseforge_loader(loader_id: str) -> tuple[str, str]:
    """``forge-47.2.0`` -> ('forge', '47.2.0'); ``neoforge-21.1.1`` etc."""
    m = re.match(r"(fabric|forge|neoforge|quilt)-(.+)", loader_id or "")
    if not m:
        return "vanilla", ""
    return m.group(1), m.group(2)
