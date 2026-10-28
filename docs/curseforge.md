# Modpacks von CurseForge einfügen

CurseForge verlangt einen **API-Key** für automatische Downloads. Den trägst
du einmalig im Panel ein, danach funktioniert alles wie bei Modrinth.

## 1. API-Key holen (einmalig, kostenlos)

1. <https://console.curseforge.com/> öffnen und anmelden.
2. Unter **API Keys** einen Key erzeugen.
3. Key kopieren.

> Hinweis: Der Key ist ein Zugangsgeheimnis. Er wird nur lokal im Panel
> (`/opt/mc-modpack-data/config.json`) gespeichert, nie geteilt.

## 2. Key im Panel eintragen

1. Panel öffnen → **Settings**.
2. Feld **CurseForge API key** ausfüllen → **Save settings**.

## 3. Modpack einfügen

### Per Link oder ID
- Projekt-URL, z. B. `https://www.curseforge.com/minecraft/modpacks/all-the-mods-10`
- oder der Slug `all-the-mods-10`
- oder eine Datei-URL `.../files/1234567` (genau diese Version)

Feld "Link or ID" ausfüllen → **"Install from link/ID"**.

### Per Datei
1. Modpack-Zip von CurseForge herunterladen (die Client/Server-Zip mit `manifest.json`).
2. Panel-Tab **CurseForge** → Datei wählen → **"Install from file"**.

## Wenn Mods fehlen

Manche Autoren **sperren Drittanbieter-Downloads**. Diese Mods kann keine
API automatisch laden. Das Panel listet sie im Install-Log als Warnung
(`project … file … — author may have disabled external downloads`).

Lösung: die betroffenen `.jar`-Dateien manuell von der CurseForge-Seite
laden und in `/opt/mc-modpack-data/server/mods/` ablegen, dann Server neu
starten.
