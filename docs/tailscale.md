# Zugriff über Tailscale

Das Panel lauscht auf `0.0.0.0:8080`, ist also über jede IP des Containers
erreichbar — auch über die Tailnet-IP. So kommst du von überall sicher ran,
ohne Ports im Router zu öffnen.

## Tailscale gleich mitinstallieren

Beim Erstellen des Containers:

```bash
INSTALL_TAILSCALE=yes bash -c "$(wget -qLO - https://raw.githubusercontent.com/Ollleey/EasyMC/main/ct/mc-modpack.sh)"
```

## Tailscale nachträglich einrichten

Im Container (oder vom Host per `pct exec <CTID> -- ...`):

```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
```

Den angezeigten Login-Link im Browser öffnen und den Container deinem
Tailnet hinzufügen.

## Panel über Tailscale öffnen

- Tailnet-IP ermitteln: `tailscale ip -4`
- Dann im Browser: `http://<tailnet-ip>:8080`
- Mit **MagicDNS** geht auch `http://<hostname>:8080` (z. B. `http://mc-modpack:8080`).

## Panel nur im Tailnet erreichbar machen (optional, sicherer)

Standardmäßig ist das Panel auch im lokalen LAN erreichbar. Willst du es
ausschließlich übers Tailnet anbieten, binde den Dienst an die Tailscale-IP:

1. `/etc/systemd/system/mc-modpack-panel.service` bearbeiten,
   im `ExecStart` `--host 0.0.0.0` durch `--host <tailnet-ip>` ersetzen.
2. `systemctl daemon-reload && systemctl restart mc-modpack-panel`

Noch strenger: zusätzlich mit `tailscale serve` nur im Tailnet veröffentlichen.
