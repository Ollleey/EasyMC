# Live-Map (Web-Karte) einrichten

Eine Live-Map ist eine **serverseitige Mod**, die eine Web-Karte deiner Welt
in den Browser bringt. Empfohlen: **BlueMap** (3D, rendert modded Blocks
weitgehend automatisch). Alternative: **Dynmap** (2D).

Das Panel bettet die Karte nur ein — die Mod selbst lädst du von der jeweiligen
Quelle.

## Modded Blocks

**BlueMap** liest die Block-Modelle und Texturen direkt aus den Mod-`.jar`s und
stellt die meisten **von Mods hinzugefügten Blöcke** korrekt dar — ohne
Zusatzarbeit. Ausnahmen: Blöcke mit komplett eigenem Renderer / Block-Entity
(z. B. manche Maschinen, animierte Blöcke) werden vereinfacht oder gar nicht
gezeichnet. Dynmap braucht für modded Blocks mehr Handarbeit und kann sie oft
nur unvollständig.

→ Für Modpacks ist **BlueMap** die bessere Wahl.

## 1. Map-Mod installieren

1. Passende BlueMap-Version für **Loader + MC-Version** deines Packs laden:
   - Modrinth: <https://modrinth.com/plugin/bluemap> (Fabric/Forge/NeoForge/Quilt)
2. Im Panel Kasten **Extra mods** → `.jar` hochladen → **Upload mod**.
3. **Restart** drücken. Beim ersten Start rendert BlueMap die Welt — das kann
   je nach Weltgröße dauern.

## 2. Live-Map im Panel aktivieren

1. Panel → **Settings**.
2. **Live map port** auf den Port der Mod setzen (**BlueMap: 8100**, Dynmap: 8123).
3. Haken **„Live map"** setzen → **Save settings**.
4. Oben erscheint die Karte eingebettet, plus **„open in new tab ↗"**.

Die Panel-Einbindung baut die Adresse automatisch aus demselben Host, über den
du das Panel aufrufst — funktioniert also direkt auch **über Tailscale**
(`http://<host>:8100`).

## 3. Port erreichbar machen

- **Im LXC** ist standardmäßig keine Firewall aktiv — der Port ist sofort offen.
- **Proxmox-Firewall** an? Dann für den Container TCP `8100` (bzw. deinen Port)
  freigeben.
- **Über Tailscale**: nichts weiter nötig, der Port ist über die Tailnet-IP
  erreichbar.
- Manche Map-Mods setzen `X-Frame-Options`, was das Einbetten blockiert. Dann
  nutzt du den **„open in new tab"**-Link — die Karte funktioniert dort normal.

## Hinweis

BlueMap lädt beim ersten Start einmalig Rendering-Ressourcen aus dem Netz.
Der Container braucht dafür Internetzugang.
