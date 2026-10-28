# Modpacks von Modrinth einfügen

Modrinth braucht **keinen** API-Key. Es gibt zwei Wege.

## A) Per Link oder ID

1. Modpack auf <https://modrinth.com/modpacks> öffnen.
2. Eine dieser Angaben ins Panel-Feld "Link or ID" einfügen:
   - die Projekt-URL, z. B. `https://modrinth.com/modpack/fabulously-optimized`
   - den Projekt-Slug, z. B. `fabulously-optimized`
   - eine bestimmte Version-URL, z. B. `.../version/abcd1234` (installiert genau diese Version)
3. **"Install from link/ID"** klicken.

Ohne Versionsangabe wird automatisch die **neueste** Version genommen.

## B) Per Datei

1. Auf der Modrinth-Projektseite unter **Versions** eine `.mrpack`-Datei herunterladen.
2. Im Panel Tab **Modrinth**, dann Datei unter "Pack file (.mrpack)" wählen.
3. **"Install from file"** klicken.

## Was dabei passiert

- Das Panel liest `modrinth.index.json` aus dem Pack.
- Es erkennt Loader (Fabric/Forge/NeoForge/Quilt) und MC-Version automatisch.
- Es installiert den passenden Server-Loader.
- Es lädt alle **serverseitigen** Mods (client-only Mods werden übersprungen).
- Die `overrides`/`server-overrides` (Configs) werden in den Serverordner kopiert.

Danach: unter **Settings** die EULA akzeptieren, RAM/Port prüfen, **Start**.
