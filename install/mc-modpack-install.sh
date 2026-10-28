#!/usr/bin/env bash
#
# Runs INSIDE a Debian 12 LXC container. Installs Java, the panel and a
# systemd service, then starts the panel so the web UI is reachable the
# moment this script finishes.
#
# Usage (inside the container, as root):
#   REPO_URL=https://github.com/<you>/EasyMC bash mc-modpack-install.sh
#
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Ollleey/EasyMC}"
BRANCH="${BRANCH:-main}"
APP_DIR="/opt/mc-modpack"
DATA_DIR="/opt/mc-modpack-data"
PANEL_PORT="${PANEL_PORT:-8080}"
SERVICE_USER="mcpanel"
INSTALL_TAILSCALE="${INSTALL_TAILSCALE:-no}"

say() { echo -e "\e[32m[mc-modpack]\e[0m $*"; }

say "Updating apt and installing base packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl wget git ca-certificates gnupg python3 python3-venv \
  python3-pip tar >/dev/null

say "Installing Temurin JDKs (Adoptium)..."
mkdir -p /etc/apt/keyrings
wget -qO- https://packages.adoptium.net/artifactory/api/gpg/key/public \
  | gpg --dearmor -o /etc/apt/keyrings/adoptium.gpg
echo "deb [signed-by=/etc/apt/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(. /etc/os-release && echo "$VERSION_CODENAME") main" \
  > /etc/apt/sources.list.d/adoptium.list
apt-get update -qq
# Install several JDKs so the panel can pick the right one per modpack:
# Java 17 (MC 1.18-1.20.4), 21 (1.20.5-1.21.x) and 25 (newest). Older packs
# that need Java 8 can be added later with: apt-get install temurin-8-jdk
JDKS="${JDKS:-temurin-17-jdk temurin-21-jdk temurin-25-jdk}"
for pkg in $JDKS; do
  say "  $pkg"
  apt-get install -y -qq "$pkg" >/dev/null || say "  (skipped $pkg — not available)"
done
java -version 2>&1 | head -1 || true

say "Fetching panel from ${REPO_URL} (${BRANCH})..."
rm -rf "$APP_DIR"
git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$APP_DIR"

say "Creating service user and data directory..."
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd -r -m -d /var/lib/mcpanel -s /usr/sbin/nologin "$SERVICE_USER"
mkdir -p "$DATA_DIR"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$DATA_DIR" "$APP_DIR"

say "Creating Python virtualenv and installing dependencies..."
python3 -m venv "$APP_DIR/panel/.venv"
"$APP_DIR/panel/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/panel/.venv/bin/pip" install -q -r "$APP_DIR/panel/requirements.txt"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"

say "Installing systemd service..."
sed -e "s#@APP_DIR@#$APP_DIR#g" \
    -e "s#@DATA_DIR@#$DATA_DIR#g" \
    -e "s#@USER@#$SERVICE_USER#g" \
    -e "s#@PORT@#$PANEL_PORT#g" \
    "$APP_DIR/systemd/mc-modpack-panel.service" > /etc/systemd/system/mc-modpack-panel.service

systemctl daemon-reload
systemctl enable --now mc-modpack-panel.service

if [[ "$INSTALL_TAILSCALE" == "yes" ]]; then
  say "Installing Tailscale..."
  curl -fsSL https://tailscale.com/install.sh | sh
  say "Run 'tailscale up' to connect this container to your tailnet."
fi

sleep 2
IP="$(hostname -I | awk '{print $1}')"
echo
say "Done. The panel is running."
echo "    ----------------------------------------------------"
echo "    Open:   http://${IP}:${PANEL_PORT}"
echo "    (Over Tailscale use this container's tailnet IP/name)"
echo "    First visit: set your panel password, then add a modpack."
echo "    ----------------------------------------------------"
