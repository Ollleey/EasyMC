# Tutorial: Modded-Minecraft-Server auf Proxmox — von null bis spielen

Dieses Tutorial führt dich lückenlos durch:
Container erstellen → Panel öffnen → Modpack einfügen → Server starten →
**mit Minecraft verbinden** → eigene Mods hinzufügen → sichern.

Lies es einmal von oben nach unten. Jeder Schritt sagt genau, wo du bist und
was als Nächstes kommt.

---

## 0. Voraussetzungen

Bevor du anfängst, brauchst du:

1. **Proxmox VE 8** (läuft bereits, du kommst auf die Weboberfläche oder per SSH auf den Host).
2. **Internet im Container** — der Container lädt Java, Mods und Loader aus dem Netz.
   Die meisten Heimnetze erfüllen das automatisch (DHCP + Internet über `vmbr0`).
3. **Genug RAM frei** auf dem Proxmox-Host. Faustregel:

   | Modpack-Größe          | Server-RAM (`-Xmx`) | Container-RAM (`RAM=`) |
   |------------------------|---------------------|------------------------|
   | klein (< 80 Mods)      | 4 GB                | 5 GB (`5120`)          |
   | mittel (80–200 Mods)   | 6 GB                | 7 GB (`7168`)          |
   | groß (200+ Mods)       | 8–10 GB             | 9–11 GB (`9216`+)      |

   > Der Container braucht immer etwa **1 GB mehr** als der Server-RAM, für
   > das Betriebssystem.

4. **Das Repo liegt auf GitHub** (öffentlich), damit der Ein-Befehl-Installer
   per `wget` funktioniert.
   *Noch nicht gepusht?* Dann überspringe Schritt 1 und nutze den
   Abschnitt **„Alternative: ohne GitHub installieren"** am Ende.

---

## 1. Container erstellen (ein Befehl auf dem Proxmox-Host)

1. Öffne eine **Shell auf dem Proxmox-Host**:
   In der Proxmox-Weboberfläche links den Host-Knoten (z. B. `pve`) anklicken →
   oben **>_ Shell**. Oder per SSH: `ssh root@<proxmox-ip>`.

2. Führe diesen Befehl aus (Werte nach Bedarf anpassen):

   ```bash
   RAM=7168 CORES=4 DISK=20 \
     bash -c "$(wget -qLO - https://raw.githubusercontent.com/Ollleey/EasyMC/main/ct/mc-modpack.sh)"
   ```

   Willst du gleich Fernzugriff über Tailscale, hänge `INSTALL_TAILSCALE=yes`
   vorne dran.

3. Das Skript dauert **3–6 Minuten**. Es lädt die Debian-Vorlage, erstellt den
   LXC, installiert Java und das Panel und startet es.

4. **Am Ende gibt es die URL aus**, etwa:

   ```
   ========================================================
   Container:  120 (mc-modpack)
   Web UI:     http://192.168.1.50:8080
   ========================================================
   ```

   Diese Adresse brauchst du gleich. **Notiere sie.**

---

## 2. Panel öffnen und Passwort setzen

1. Öffne die URL aus Schritt 1 im Browser, z. B. `http://192.168.1.50:8080`.
2. Beim **ersten Besuch** erscheint „First run — choose a panel password".
   Tippe ein Passwort ein und klicke **„Set password & enter"**.
   Dieses Passwort gilt ab jetzt für jeden Login.
3. Danach kommt der **Erst-Setup-Assistent**: RAM und Port setzen, EULA
   bestätigen und die gewünschten Funktionen **an- oder abwählen** (Backups,
   RCON, Live-Map, Discord, geplanter Neustart). Alles ist optional und später
   unter **Settings** änderbar. Mit **„Finish setup →"** geht's weiter.
4. Du landest auf dem **Dashboard**. Oben siehst du den Server-Status
   (`● stopped`).

---

## 3. (Nur CurseForge) API-Key eintragen

Modrinth-Packs brauchen **keinen** Key — überspringe diesen Schritt dann.

Für CurseForge-Packs einmalig:

1. <https://console.curseforge.com/> öffnen, anmelden, unter **API Keys**
   einen Key erzeugen, kopieren.
2. Im Panel nach unten zu **Settings** scrollen.
3. Key ins Feld **„CurseForge API key"** einfügen → **„Save settings"**.

---

## 4. Modpack einfügen

Im Dashboard oben rechts der Kasten **„Install a modpack"**.
Oben wählst du die Plattform: Tab **Modrinth** oder **CurseForge**.

### Variante A — per Link oder ID

1. Modpack-Seite öffnen:
   - Modrinth: <https://modrinth.com/modpacks>
   - CurseForge: <https://www.curseforge.com/minecraft/modpacks>
2. Die **URL der Modpack-Seite kopieren** (z. B.
   `https://modrinth.com/modpack/fabulously-optimized`).
3. Im Panel ins Feld **„Link or ID"** einfügen.
4. **„Install from link/ID"** klicken.

### Variante B — per Datei

1. Pack-Datei herunterladen:
   - Modrinth: auf der Projektseite unter **Versions** eine `.mrpack`-Datei.
   - CurseForge: die Modpack-**Zip** (die mit `manifest.json`).
2. Im Panel passenden Tab wählen → **„Choose File"** → Datei auswählen.
3. **„Install from file"** klicken.

### Was jetzt passiert

Unter dem Kasten läuft ein **Install-Log** mit. Das Panel:

1. erkennt Loader (Fabric/Forge/NeoForge/Quilt) und MC-Version automatisch,
2. installiert den passenden Server-Loader,
3. lädt alle serverseitigen Mods,
4. kopiert die Configs des Packs.

Warte, bis dort `Done: <Packname> ... , N files.` steht. **Warnungen** (`WARN:`)
bedeuten einzelne nicht ladbare Mods — siehe Abschnitt 8.

---

## 5. EULA akzeptieren und Einstellungen prüfen

1. Zu **Settings** scrollen.
2. **RAM (MB)** prüfen/setzen (siehe Tabelle in Schritt 0, z. B. `6144`).
3. **Server port** prüfen (Standard `25565`).
4. Haken bei **„I accept the Minecraft EULA"** setzen (Pflicht, sonst startet
   der Server nicht).
5. **„Save settings"** klicken.

---

## 6. Server starten

1. Oben links im Kasten **„Server"** auf **Start** klicken.
2. In der **Console** siehst du live das Hochfahren. Beim ersten Start von
   Forge/NeoForge werden Bibliotheken nachgeladen — das kann 1–3 Minuten dauern.
3. Fertig ist der Server, wenn in der Konsole eine Zeile wie
   `Done (23.4s)! For help, type "help"` erscheint und der Status oben auf
   **`● running`** springt.

> Stürzt der Server ab, startet das Panel ihn automatisch neu (sofern
> „Auto-restart on crash" an ist). Die Ursache steht in der Konsole.

---

## 7. Mit dem Server verbinden (Minecraft-Client)

Du brauchst auf deinem **Spiel-PC** denselben Loader und dasselbe Modpack wie
auf dem Server.

1. **Modpack im Launcher installieren** (Client-Seite):
   - Modrinth: im **Modrinth App**-Launcher dasselbe Pack installieren.
   - CurseForge: im **CurseForge/Overwolf**-Launcher dasselbe Pack installieren.
   - Beide sorgen dafür, dass dein Client Loader + Version passend hat.
2. Minecraft mit diesem Pack-Profil starten.
3. **Mehrspieler → Server hinzufügen.**
4. Als Serveradresse eintragen:
   - **Im selben Heimnetz:** die Container-IP mit Port, z. B.
     `192.168.1.50:25565` (Port weglassen, wenn `25565`).
   - **Über Tailscale (von überall):** die Tailnet-IP oder den MagicDNS-Namen,
     z. B. `mc-modpack:25565` — siehe `docs/tailscale.md`.
   - **Für Freunde außerhalb ohne Tailscale:** entweder Freunde ins Tailnet
     einladen (einfach, sicher), oder am Router Port `25565` auf die
     Container-IP weiterleiten (Portfreigabe).
5. **Beitreten.**

---

## 8. Eigene Mods zusätzlich hinzufügen

Im Panel gibt es dafür den Kasten **„Extra mods"**. Diese Mods landen in
einem eigenen, dauerhaften Ordner (`/opt/mc-modpack-data/extra-mods`) und
werden **bei jedem Modpack-Update automatisch wieder eingespielt** — sie gehen
also nicht verloren.

1. Mod als `.jar` besorgen. **Muss passen:** gleicher Loader, gleiche
   MC-Version, **serverseitig lauffähig**, inklusive Abhängigkeiten.
2. Im Panel Kasten **„Extra mods"** → **„Add mod (.jar)"** → Datei wählen →
   **„Upload mod"**. Der Mod wird sofort auch in den laufenden Serverordner kopiert.
3. Im Panel **Restart** drücken, damit der Server den Mod lädt.

In der Liste zeigt ein **grüner Punkt**, dass der Mod aktuell im Server aktiv
ist. Über **„remove"** löschst du ihn wieder (aus dem Extra-Ordner und dem
Serverordner).

> **Hinweis:** Reine Client-Mods (Shader, Minimap) gehören **nicht** hierher —
> sie bringen auf dem Server nichts oder stürzen ihn ab. Die kommen nur in
> deinen Spiel-Client.
>
> Wer lieber direkt auf die Dateien zugreift, kann `.jar` auch vom Host
> ablegen: `pct push <CTID> ./meinmod.jar /opt/mc-modpack-data/extra-mods/meinmod.jar`.

---

## 9. server.properties anpassen (optional)

Ganz unten im Panel der Kasten **„server.properties"**.

1. Text bearbeiten, z. B.:
   ```
   motd=Mein Modpack-Server
   max-players=10
   difficulty=normal
   view-distance=10
   ```
2. **„Save properties"** klicken.
3. Server **neu starten** (Restart), damit die Änderungen greifen.

> Den **Port** nicht hier, sondern unter **Settings** ändern — das Panel hält
> `server-port` beim Start automatisch synchron.

---

## 10. Spielerverwaltung (Whitelist, Admins, Bans)

Im Panel der Kasten **„Players"**.

- **Whitelist an/aus:** Haken **„Whitelist on"**. Bei aktiver Whitelist dürfen
  nur gelistete Spieler joinen.
- **Spieler zur Whitelist:** Name eintippen → **Add**. Entfernen über **remove**.
- **Operators (Admins):** Name → **Op** macht einen Spieler zum Server-Admin
  (Zugriff auf Befehle). **remove** nimmt die Rechte wieder.
- **Bans:** Name → **Ban** sperrt einen Spieler. **remove** hebt den Bann auf.
- **Online:** Oben rechts steht, wer gerade verbunden ist.

> **Wichtig:** Ops und Bans brauchen einen **laufenden Server** (sie gehen über
> die Server-Konsole). Die **Whitelist** kannst du auch bei gestopptem Server
> bearbeiten — Namen werden dann über Mojang aufgelöst.

---

## 11. Live-Map (optional)

Du kannst eine Web-Karte deiner Welt im Panel einbetten:

1. Map-Mod **BlueMap** (rendert modded Blocks weitgehend automatisch) als
   **Extra mod** hochladen, passend zu Loader + MC-Version → **Restart**.
2. Panel → **Settings** → **Live map port** = `8100` (BlueMap) → Haken
   **„Live map"** → **Save settings**.
3. Oben erscheint die Karte, plus „open in new tab". Funktioniert auch über
   Tailscale (`http://<host>:8100`).

Details, inkl. was bei modded Blocks geht: [docs/livemap.md](docs/livemap.md).

---

## 12. Backups

### Im Panel (empfohlen)

Kasten **„Backups"**:

- **Backup now** — sichert sofort die Welt(en) + `server.properties` als
  `.tar.gz`.
- **Automatische Backups** — unter **Settings**: Haken „Automatic backups",
  Intervall in Stunden und „Keep last N backups" (ältere werden automatisch
  gelöscht).
- Jeder Eintrag hat **restore** (Welt zurückspielen — Server wird dafür
  gestoppt) und **delete**.

Die Archive liegen im Container unter `/opt/mc-modpack-data/backups/`.

### Alternative: ganzer Container

Noch umfassender ist ein Proxmox-Container-Backup:
Container auswählen → **Backup** → **Backup now**. Sichert alles auf einmal
(inkl. Mods, Config, Loader).

---

## 13. Weitere Panel-Funktionen (Kurzüberblick)

- **Live-Stats:** Oben im Server-Kasten siehst du RAM-Nutzung, Uptime und
  Spielerzahl live.
- **Geplante Neustarts:** Settings → „Daily scheduled restart" + Uhrzeit +
  Vorwarn-Minuten. Der Server warnt Spieler im Chat und startet dann neu.
- **Discord-Benachrichtigungen:** Webhook eintragen → Meldungen bei
  Start/Stopp/Crash und Join/Leave. Siehe [docs/discord.md](docs/discord.md).
- **Mod-Browser:** Im Extra-mods-Kasten „search Modrinth" — einzelne Mods
  suchen und per **add** hinzufügen (passend zu Loader + MC-Version).
- **Welt importieren:** Kasten „World & appearance" → eigene Welt-`.zip`
  hochladen (Server stoppt, Sicherheits-Backup wird gemacht).
- **Server-Icon:** 64×64-PNG hochladen (gleicher Kasten).
- **Config-Editor:** Kasten „Config files" → Config-Dateien direkt im Panel
  bearbeiten.
- **Performance:** Settings → „use Aikar flags" setzt bewährte JVM-Flags,
  skaliert auf deinen RAM. **RCON** (Standard an) hält Stat-Abfragen aus der
  Konsole raus.
- **Welt-Download:** Kasten „World & appearance" → aktuelle Welt als `.zip`
  herunterladen (Umzug/Sicherung).
- **Geplante Befehle:** Kasten „Scheduled commands" → täglich zu fester
  Uhrzeit einen Konsolenbefehl ausführen (z. B. `save-all`).
- **Tunnel für Freunde:** Kasten „Tunnel (playit.gg)" → beitreten ohne
  Portfreigabe. Siehe [docs/tunnel.md](docs/tunnel.md).
- **1-Klick BlueMap:** Im Extra-mods-Kasten installiert „1-click BlueMap" die
  passende Map-Mod und aktiviert die Live-Map.
- **Crash-Reports & Logs:** Kasten „Crash reports & logs" → Crash-Berichte und
  `latest.log` direkt im Panel ansehen.
- **Live-CPU:** Zusätzliche Kachel oben zeigt die CPU-Last des Servers.
- **Playtime:** Kasten „Playtime" → Spielzeit pro Spieler (läuft mit, solange
  das Panel läuft).
- **Chunk-Vorgenerierung:** Kasten „World pre-generation" → Chunky per Klick
  installieren, Radius setzen, vorgenerieren (weniger Lag beim Erkunden).
- **Als App installieren (PWA):** Im Browser „Zum Startbildschirm hinzufügen" /
  „Installieren" — das Panel öffnet dann im Vollbild wie eine App.

---

## 14. Server verwalten (im Container)

Per `pct exec <CTID> -- <befehl>` vom Host, oder direkt im Container
(`pct enter <CTID>`):

```bash
systemctl status mc-modpack-panel      # läuft das Panel?
systemctl restart mc-modpack-panel     # Panel neu starten
journalctl -u mc-modpack-panel -f      # Panel-Logs live
```

Der **Minecraft-Server** selbst wird über das Panel gesteuert
(Start/Stop/Restart), nicht über systemd.

**Panel aktualisieren** (neue Version aus dem Repo):

```bash
pct exec <CTID> -- bash -c "cd /opt/mc-modpack && git pull && \
  /opt/mc-modpack/panel/.venv/bin/pip install -q -r panel/requirements.txt && \
  systemctl restart mc-modpack-panel"
```

---

## 15. Probleme?

Siehe [docs/troubleshooting.md](docs/troubleshooting.md). Häufigste Fälle:

- Server startet nicht → EULA-Haken fehlt, oder zu wenig RAM.
- Panel nicht erreichbar → `systemctl status mc-modpack-panel`.
- CurseForge-Mod fehlt → Autor hat Download gesperrt, Mod manuell nachlegen.
- Altes Pack (MC ≤ 1.16) → braucht älteres Java, siehe Troubleshooting.

---

## Alternative: ohne GitHub installieren

Ist das Repo (noch) nicht auf GitHub, kannst du das Panel auch lokal testen
oder die Dateien manuell in den Container kopieren.

**Lokal testen (auf jedem Linux/Mac mit Python 3):**

```bash
cd panel
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
MCPANEL_DATA=./data uvicorn mcpanel.main:app --host 0.0.0.0 --port 8080
```

Dann `http://localhost:8080` öffnen. (Zum echten Serverbetrieb brauchst du
Java 21 auf dem System.)

**Manuell in einen bestehenden LXC kopieren:**
Dateien per `pct push` oder `scp` nach `/opt/mc-modpack` legen und
`install/mc-modpack-install.sh` im Container ausführen (es klont sonst selbst,
setze dann `REPO_URL` auf deine Quelle).
