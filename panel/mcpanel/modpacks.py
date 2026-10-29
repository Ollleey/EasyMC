"""Download and install modpacks from Modrinth and CurseForge.

Two source shapes are supported for each platform:

* a link or project/version id -> we resolve and download the pack, then
  install it exactly like an uploaded file;
* an uploaded pack file (``.mrpack`` for Modrinth, ``.zip`` for CurseForge).

Installation always ends with the server directory holding the mods,
configs and the right loader, plus a short human-readable report listing
anything that could not be fetched automatically.
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import config, loaders

MODRINTH_API = "https://api.modrinth.com/v2"
CURSEFORGE_API = "https://api.curseforge.com/v1"
USER_AGENT = "EasyMC/1.0 (self-hosted panel)"
TIMEOUT = httpx.Timeout(120.0, connect=30.0)


@dataclass
class InstallResult:
    pack_name: str
    loader: str
    minecraft_version: str
    loader_version: str
    files_installed: int = 0
    warnings: list[str] = field(default_factory=list)


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )


def _safe_target(server_dir: Path, rel: str) -> Path | None:
    """Join ``rel`` under ``server_dir`` but reject path traversal (Zip Slip).

    Returns the resolved path, or None if the entry would escape the server
    directory (absolute path, ``..``, symlink tricks). Callers skip None.
    """
    base = server_dir.resolve()
    target = (base / rel).resolve()
    if target == base or base in target.parents:
        return target
    return None


def _clean_server_dir(server_dir: Path) -> None:
    """Remove previous mod set but keep worlds and panel-managed files."""
    keep = {"world", "world_nether", "world_the_end", "server.properties",
            "ops.json", "whitelist.json", "banned-players.json",
            "banned-ips.json", "usercache.json", "eula.txt"}
    if not server_dir.exists():
        server_dir.mkdir(parents=True, exist_ok=True)
        return
    for child in server_dir.iterdir():
        if child.name in keep:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def _extract_overrides(zf: zipfile.ZipFile, server_dir: Path) -> None:
    """Copy ``overrides/`` and ``server-overrides/`` into the server dir.

    ``server-overrides`` wins over ``overrides`` when both touch a path.
    """
    for prefix in ("overrides/", "server-overrides/"):
        for name in zf.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            rel = name[len(prefix):]
            target = _safe_target(server_dir, rel)
            if target is None:
                continue        # skip entries that try to escape (Zip Slip)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def search_modrinth_mods(query: str, mc_version: str, loader: str) -> list[dict]:
    """Search Modrinth for individual mods matching the pack's MC + loader."""
    facets = [["project_type:mod"]]
    if mc_version:
        facets.append([f"versions:{mc_version}"])
    if loader and loader != "vanilla":
        facets.append([f"categories:{loader}"])
    with _client() as client:
        r = client.get(
            f"{MODRINTH_API}/search",
            params={"query": query, "facets": json.dumps(facets), "limit": 20},
        )
        r.raise_for_status()
        return [
            {
                "project_id": h["project_id"],
                "slug": h["slug"],
                "title": h["title"],
                "description": h["description"],
                "downloads": h.get("downloads", 0),
                "icon_url": h.get("icon_url", ""),
            }
            for h in r.json().get("hits", [])
        ]


def add_mod_from_modrinth(
    project_id: str, mc_version: str, loader: str, dest_dir: Path
) -> str:
    """Download the latest compatible version of a mod into ``dest_dir``.

    Returns the saved filename. Raises if nothing matches.
    """
    params = {}
    if loader and loader != "vanilla":
        params["loaders"] = json.dumps([loader])
    if mc_version:
        params["game_versions"] = json.dumps([mc_version])
    with _client() as client:
        r = client.get(f"{MODRINTH_API}/project/{project_id}/version", params=params)
        r.raise_for_status()
        versions = r.json()
        if not versions:
            raise RuntimeError("No version of this mod matches your loader/MC version.")
        files = versions[0]["files"]
        primary = next((f for f in files if f.get("primary")), files[0])
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / primary["filename"]
        _download_to(client, primary["url"], dest)
        return primary["filename"]


def apply_extra_mods(server_dir: Path) -> int:
    """Copy user-added mods from the persistent extra-mods dir into mods/.

    Called after every modpack install so manually added mods survive a
    reinstall or update. Returns how many mods were applied.
    """
    src = config.EXTRA_MODS_DIR
    if not src.exists():
        return 0
    dst = server_dir / "mods"
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for jar in src.glob("*.jar"):
        shutil.copy2(jar, dst / jar.name)
        count += 1
    return count


def _download_to(client: httpx.Client, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)


# ==========================================================================
# Modrinth
# ==========================================================================
_MODRINTH_SLUG = re.compile(r"modrinth\.com/(?:modpack|project)/([^/?#]+)")
_MODRINTH_VERSION = re.compile(r"/version/([^/?#]+)")


def resolve_modrinth(link_or_id: str, dest: Path) -> str:
    """Download an ``.mrpack`` for a Modrinth link, slug, project or version id.

    Returns the pack display name.
    """
    with _client() as client:
        version_id = None
        slug = link_or_id.strip()
        m = _MODRINTH_VERSION.search(link_or_id)
        if m:
            version_id = m.group(1)
        m = _MODRINTH_SLUG.search(link_or_id)
        if m:
            slug = m.group(1)

        if version_id:
            version = client.get(f"{MODRINTH_API}/version/{version_id}").json()
        else:
            # Treat the input as a project slug/id and take the latest version.
            project = client.get(f"{MODRINTH_API}/project/{slug}")
            project.raise_for_status()
            versions = client.get(
                f"{MODRINTH_API}/project/{slug}/version"
            ).json()
            if not versions:
                raise RuntimeError("No versions found for this Modrinth project.")
            version = versions[0]

        mrpack_file = next(
            (f for f in version["files"] if f["filename"].endswith(".mrpack")),
            version["files"][0],
        )
        _download_to(client, mrpack_file["url"], dest)
        return version.get("name") or slug


def install_mrpack(mrpack_path: Path, server_dir: Path) -> InstallResult:
    with zipfile.ZipFile(mrpack_path) as zf:
        index = json.loads(zf.read("modrinth.index.json"))
        loader, mc, loader_ver = loaders.detect_loader_from_mrpack(
            index.get("dependencies", {})
        )
        _clean_server_dir(server_dir)
        loaders.install_loader(loader, mc, loader_ver, server_dir)

        result = InstallResult(
            pack_name=index.get("name", mrpack_path.stem),
            loader=loader, minecraft_version=mc, loader_version=loader_ver,
        )
        with _client() as client:
            for entry in index.get("files", []):
                env = entry.get("env", {})
                if env.get("server") == "unsupported":
                    continue
                target = _safe_target(server_dir, entry["path"])
                if target is None:
                    result.warnings.append(f"Skipped unsafe path: {entry['path']}")
                    continue
                urls = entry.get("downloads", [])
                if not urls:
                    result.warnings.append(f"No download URL for {entry['path']}")
                    continue
                try:
                    _download_to(client, urls[0], target)
                    result.files_installed += 1
                except httpx.HTTPError as exc:
                    result.warnings.append(f"Failed: {entry['path']} ({exc})")
        _extract_overrides(zf, server_dir)
    return result


# ==========================================================================
# CurseForge
# ==========================================================================
_CF_SLUG = re.compile(r"curseforge\.com/minecraft/modpacks/([^/?#]+)")
_CF_FILE = re.compile(r"/(?:files|download)/(\d+)")


def _cf_headers(api_key: str) -> dict:
    if not api_key:
        raise RuntimeError(
            "CurseForge API key missing. Set it under Settings -> see docs/curseforge.md."
        )
    return {"x-api-key": api_key, "User-Agent": USER_AGENT, "Accept": "application/json"}


def _cf_edge_url(file_id: int, file_name: str) -> str:
    """Fallback CDN URL when the API returns a null downloadUrl."""
    fid = str(file_id)
    return f"https://edge.forgecdn.net/files/{fid[:4]}/{int(fid[4:])}/{file_name}"


def resolve_curseforge(link_or_id: str, api_key: str, dest: Path) -> str:
    """Resolve a CurseForge modpack link/id to a downloaded pack zip."""
    headers = _cf_headers(api_key)
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        file_id = None
        m = _CF_FILE.search(link_or_id)
        if m:
            file_id = int(m.group(1))

        mod_id = None
        if link_or_id.strip().isdigit():
            mod_id = int(link_or_id.strip())
        else:
            m = _CF_SLUG.search(link_or_id)
            slug = m.group(1) if m else link_or_id.strip()
            search = client.get(
                f"{CURSEFORGE_API}/mods/search",
                params={"gameId": 432, "classId": 4471, "slug": slug},
            ).json()
            hits = search.get("data", [])
            if not hits:
                raise RuntimeError(f"CurseForge modpack not found: {slug}")
            mod_id = hits[0]["id"]

        if file_id is None:
            mod = client.get(f"{CURSEFORGE_API}/mods/{mod_id}").json()["data"]
            file_id = mod["mainFileId"]
            pack_name = mod.get("name", str(mod_id))
        else:
            pack_name = str(mod_id or file_id)

        finfo = client.get(
            f"{CURSEFORGE_API}/mods/{mod_id}/files/{file_id}"
        ).json()["data"]
        url = finfo.get("downloadUrl") or _cf_edge_url(file_id, finfo["fileName"])
        _download_to(client, url, dest)
        return pack_name


def install_curseforge_zip(
    zip_path: Path, api_key: str, server_dir: Path
) -> InstallResult:
    headers = _cf_headers(api_key)
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        mc = manifest["minecraft"]["version"]
        primary = next(
            (l for l in manifest["minecraft"]["modLoaders"] if l.get("primary")),
            manifest["minecraft"]["modLoaders"][0],
        )
        loader, loader_ver = loaders.parse_curseforge_loader(primary["id"])

        _clean_server_dir(server_dir)
        loaders.install_loader(loader, mc, loader_ver, server_dir)

        result = InstallResult(
            pack_name=manifest.get("name", zip_path.stem),
            loader=loader, minecraft_version=mc, loader_version=loader_ver,
        )
        with httpx.Client(
            timeout=TIMEOUT, follow_redirects=True, headers=headers
        ) as client:
            for entry in manifest.get("files", []):
                project_id, file_id = entry["projectID"], entry["fileID"]
                try:
                    finfo = client.get(
                        f"{CURSEFORGE_API}/mods/{project_id}/files/{file_id}"
                    ).json()["data"]
                    name = finfo["fileName"]
                    target = _safe_target(server_dir, f"mods/{name}")
                    if target is None:
                        result.warnings.append(f"Skipped unsafe mod name: {name}")
                        continue
                    url = finfo.get("downloadUrl") or _cf_edge_url(file_id, name)
                    _download_to(client, url, target)
                    result.files_installed += 1
                except httpx.HTTPError:
                    # Many CF authors disable third-party downloads; tell the user.
                    result.warnings.append(
                        f"Could not download project {project_id} file {file_id}. "
                        "The author may have disabled external downloads."
                    )

        override_dir = manifest.get("overrides", "overrides")
        for name in zf.namelist():
            if not name.startswith(f"{override_dir}/") or name.endswith("/"):
                continue
            rel = name[len(override_dir) + 1:]
            target = _safe_target(server_dir, rel)
            if target is None:
                continue        # skip entries that try to escape (Zip Slip)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return result
