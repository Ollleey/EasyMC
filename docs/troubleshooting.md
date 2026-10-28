# Fehlerbehebung

## Panel nicht erreichbar

```bash
systemctl status mc-modpack-panel
journalctl -u mc-modpack-panel -n 50 --no-pager
```

- Läuft der Dienst? Sonst `systemctl restart mc-modpack-panel`.
- Richtige IP? Im Container `hostname -I`.
- Firewall/Proxmox-Firewall offen für den Panel-Port (Standard 8080)?

## Server startet nicht

Im Panel die **Konsole** ansehen — die Ursache steht fast immer dort.

- **"You must accept the Minecraft EULA"** → unter Settings EULA-Haken setzen.
- **Zu wenig RAM** → unter Settings `RAM (MB)` erhöhen. Der Container braucht
  etwas mehr RAM als der Server (`-Xmx`).
- **Falsche Java-Version** (alte Packs) → siehe unten.
- **Port belegt** → anderen `Server port` wählen.

## Loader-Installation schlägt fehl

- Forge/NeoForge brauchen Internet beim ersten Start (Libraries werden geladen).
- Prüfen, ob der Container raus darf: `ping -c1 maven.neoforged.net`.
- Konsole/Install-Log im Panel zeigt die genaue Fehlermeldung.

## CurseForge: Mods fehlen

Autor hat Drittanbieter-Downloads gesperrt. `.jar` manuell nach
`/opt/mc-modpack-data/server/mods/` legen und Server neu starten.
Siehe [curseforge.md](curseforge.md).

## Alte Modpacks brauchen älteres Java

Standardmäßig ist **JDK 21** installiert. Für MC 1.16/1.17 o. ä.:

```bash
apt-get install -y temurin-17-jdk temurin-8-jdk
update-alternatives --config java   # passende Version wählen
```

Der Panel-Prozess ruft `java` aus dem `PATH` auf — die per
`update-alternatives` gewählte Version wird verwendet.

## Komplett neu aufsetzen

Daten löschen und von vorn:

```bash
systemctl stop mc-modpack-panel
rm -rf /opt/mc-modpack-data/server/*
systemctl start mc-modpack-panel
```

Welt vorher sichern, falls du sie behalten willst
(`/opt/mc-modpack-data/server/world`).
