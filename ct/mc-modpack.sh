#!/usr/bin/env bash
#
# Run this ON THE PROXMOX HOST (not inside a container).
# It creates a Debian 12 LXC, installs the MC Modpack Panel inside it and
# prints the URL. When it finishes, the web UI is already running.
#
#   bash -c "$(wget -qLO - https://raw.githubusercontent.com/Ollleey/EasyMC/main/ct/mc-modpack.sh)"
#
# Override any default with an environment variable, e.g.:
#   CTID=120 RAM=8192 DISK=20 bash mc-modpack.sh
#
set -euo pipefail

# ---- defaults (override via env) -----------------------------------------
CTID="${CTID:-}"                       # auto-picked if empty
HOSTNAME="${HOSTNAME:-mc-modpack}"
RAM="${RAM:-6144}"                     # MB for the container (server + panel)
CORES="${CORES:-4}"
DISK="${DISK:-16}"                     # GB
BRIDGE="${BRIDGE:-vmbr0}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
PANEL_PORT="${PANEL_PORT:-8080}"
REPO_URL="${REPO_URL:-https://github.com/Ollleey/EasyMC}"
BRANCH="${BRANCH:-main}"
INSTALL_TAILSCALE="${INSTALL_TAILSCALE:-no}"
PASSWORD="${PASSWORD:-}"               # root password for the container (optional)

TEMPLATE_PATTERN="${TEMPLATE_PATTERN:-debian-12-standard}"  # pick newest match

say() { echo -e "\e[36m[proxmox]\e[0m $*"; }
die() { echo -e "\e[31m[error]\e[0m $*" >&2; exit 1; }

command -v pct >/dev/null || die "pct not found. Run this on the Proxmox host."

# ---- pick a container id --------------------------------------------------
if [[ -z "$CTID" ]]; then
  CTID="$(pvesh get /cluster/nextid)"
fi
say "Using container id: $CTID"

# ---- ensure a Debian template is present ----------------------------------
# Template versions roll over in the catalogue, so never hardcode a version:
# reuse an already-downloaded one, else pick the newest matching name.
OSTEMPLATE_NAME="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null \
  | awk -v p="$TEMPLATE_PATTERN" '$1 ~ p {print $1}' \
  | sed 's#.*/##' | sort -V | tail -n1)"

if [[ -z "$OSTEMPLATE_NAME" ]]; then
  say "Downloading Debian template ($TEMPLATE_PATTERN, newest available)..."
  pveam update >/dev/null 2>&1 || true
  OSTEMPLATE_NAME="$(pveam available --section system 2>/dev/null \
    | awk -v p="$TEMPLATE_PATTERN" '$2 ~ p {print $2}' | sort -V | tail -n1)"
  [[ -n "$OSTEMPLATE_NAME" ]] || die "No '$TEMPLATE_PATTERN' template in the catalogue. Run: pveam available --section system"
  pveam download "$TEMPLATE_STORAGE" "$OSTEMPLATE_NAME"
fi
say "Using template: $OSTEMPLATE_NAME"
TEMPLATE_REF="${TEMPLATE_STORAGE}:vztmpl/${OSTEMPLATE_NAME}"

# ---- create the container -------------------------------------------------
say "Creating LXC $CTID ($HOSTNAME): ${CORES} cores, ${RAM}MB RAM, ${DISK}GB disk..."
pct create "$CTID" "$TEMPLATE_REF" \
  --hostname "$HOSTNAME" \
  --cores "$CORES" \
  --memory "$RAM" \
  --swap 512 \
  --rootfs "${STORAGE}:${DISK}" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  ${PASSWORD:+--password "$PASSWORD"}

say "Starting container..."
pct start "$CTID"

# Wait for the container to get an IP via DHCP instead of a fixed sleep.
say "Waiting for container network..."
IP=""
for _ in $(seq 1 30); do
  IP="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}')"
  [[ -n "$IP" ]] && break
  sleep 2
done
[[ -n "$IP" ]] || die "Container got no IP via DHCP. Check the bridge ($BRIDGE)."

# ---- run the installer inside the container -------------------------------
say "Installing panel inside the container (this takes a few minutes)..."
pct exec "$CTID" -- bash -c "apt-get update -qq && apt-get install -y -qq curl wget >/dev/null"
pct exec "$CTID" -- bash -c \
  "REPO_URL='$REPO_URL' BRANCH='$BRANCH' PANEL_PORT='$PANEL_PORT' INSTALL_TAILSCALE='$INSTALL_TAILSCALE' \
   bash -c \"\$(wget -qLO - $REPO_URL/raw/$BRANCH/install/mc-modpack-install.sh)\""

# ---- report ---------------------------------------------------------------
IP="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
echo
say "All done."
echo "    ========================================================"
echo "    Container:  $CTID ($HOSTNAME)"
echo "    Web UI:     http://${IP}:${PANEL_PORT}"
echo "    Open it now, set your panel password, then add a modpack."
if [[ "$INSTALL_TAILSCALE" == "yes" ]]; then
  echo "    Tailscale:  run 'pct exec $CTID -- tailscale up' to connect."
fi
echo "    ========================================================"
