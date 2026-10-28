# Proxmox MC Modpack Panel

Self-hosted **web panel for a modded Minecraft Java server**, installed into a
Proxmox **LXC container** with a single command. Add modpacks from **Modrinth
or CurseForge** by link/ID or file upload — the right loader (Fabric, Forge,
NeoForge, Quilt) and all mods are set up automatically.

When the installer finishes, **the panel is already running** and prints its
URL. Open it, set a password, add a modpack, start playing.

> Everything runs on your own hardware. The panel binds to all interfaces, so
> it's reachable on your LAN and over **Tailscale** with no extra setup.

---

## Features

| | |
|---|---|
| **Modpacks** | Modrinth (`.mrpack`) & CurseForge (zip), by link/ID or upload; auto loader setup |
| **Mods** | Modrinth mod browser, plus persistent *extra mods* that survive pack updates |
| **Control** | Start/stop/restart, live console, `server.properties` editor |
| **Live stats** | RAM, CPU, uptime and online-player tiles; per-player **playtime** |
| **Players** | Whitelist, operators, bans, online list |
| **Backups** | Manual + automatic with retention, restore in one click |
| **Automation** | Scheduled daily restart (with chat warning) and scheduled commands |
| **Live map** | Embedded BlueMap/Dynmap view (one-click BlueMap install) |
| **World** | Import and download worlds (`.zip`); world pre-generation via Chunky |
| **Sharing** | playit.gg tunnel so friends can join without port forwarding |
| **Alerts** | Discord webhook notifications (start/stop/crash, join/leave) |
| **Extras** | Server icon, config-file editor, crash-report viewer, Aikar flags, RCON |
| **Install** | Works in the browser; installable as a **PWA** (phone/desktop app) |

---

## Quick start

Run this **on the Proxmox host shell** (Datacenter → your node → Shell):

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Ollleey/EasyMC/main/ct/mc-modpack.sh)"
```

It creates a Debian 12 LXC, installs Java 21 and the panel, and starts it.
When it finishes it prints a line like:

```
Web UI:  http://192.168.1.50:8080
```

Then:

1. Open that URL and **set a panel password**.
2. Run the **first-time setup** — RAM, port, and tick/untick the features you
   want (backups, RCON, live map, Discord, scheduled restart). Everything is
   optional and changeable later under Settings.
3. **Add a modpack** (Modrinth or CurseForge — link or file).
4. Make sure the **EULA** is accepted and press **Start**.
5. Connect from Minecraft (same modpack on the client) — see
   [docs/](docs/) and the full [TUTORIAL.md](TUTORIAL.md).

### Customise the container

Set any option as an environment variable before the command:

```bash
CTID=120 RAM=8192 CORES=4 DISK=20 INSTALL_TAILSCALE=yes \
  bash -c "$(wget -qLO - https://raw.githubusercontent.com/Ollleey/EasyMC/main/ct/mc-modpack.sh)"
```

| Variable | Default | Meaning |
|---|---|---|
| `CTID` | next free | Container ID |
| `RAM` | `6144` | Container RAM (MB) — keep ~1 GB above the server's `-Xmx` |
| `CORES` | `4` | CPU cores |
| `DISK` | `16` | Disk (GB) |
| `STORAGE` | `local-lvm` | Proxmox storage for the rootfs |
| `BRIDGE` | `vmbr0` | Network bridge |
| `PANEL_PORT` | `8080` | Web panel port |
| `INSTALL_TAILSCALE` | `no` | `yes` installs Tailscale too |

---

## Requirements

- **Proxmox VE 8**, with host shell/SSH access.
- **Internet access** from the container (it downloads Java, mods and loaders).
- Enough free RAM: server `-Xmx` plus ~1 GB for the OS.

---

## Documentation

- **[TUTORIAL.md](TUTORIAL.md)** — complete step-by-step guide (German), from
  install to joining and managing the server.
- [docs/modrinth.md](docs/modrinth.md) — add Modrinth modpacks
- [docs/curseforge.md](docs/curseforge.md) — add CurseForge modpacks (API key)
- [docs/livemap.md](docs/livemap.md) — BlueMap/Dynmap live map
- [docs/tailscale.md](docs/tailscale.md) — remote access over Tailscale
- [docs/tunnel.md](docs/tunnel.md) — playit.gg tunnel for friends
- [docs/discord.md](docs/discord.md) — Discord notifications
- [docs/troubleshooting.md](docs/troubleshooting.md) — fixes for common issues

---

## How it works

- A small **FastAPI** app (Python) runs as the `mc-modpack-panel` systemd
  service and manages the Minecraft server as a child process.
- All data (world, mods, config, backups) lives under
  `/opt/mc-modpack-data` — easy to back up.
- Installing a modpack reads its index, installs the matching server loader,
  downloads the server-side mods and copies the pack's config.

---

## Run locally (without Proxmox)

```bash
cd panel
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
MCPANEL_DATA=./data uvicorn mcpanel.main:app --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080`. (Running an actual server also needs Java 21.)

---

## Notes & limits

- **Java 21** is installed. Very old packs (MC ≤ 1.16) may need Java 8/11 —
  install it in the container and select it with `update-alternatives`.
- Some **CurseForge** authors block third-party downloads; those mods are
  reported and must be added manually.
- One server per container in this version.
- Map mods (BlueMap/Dynmap), Chunky and the playit agent are downloaded from
  their own sources; the panel only installs/embeds them.

---

## License

MIT — see [LICENSE](LICENSE).
