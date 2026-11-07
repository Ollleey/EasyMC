# Tunnel für Freunde (playit.gg)

Mit einem Tunnel können Freunde beitreten, **ohne** Portfreigabe am Router und
ohne Tailscale bei den Freunden. Das Panel nutzt den kostenlosen
**playit.gg**-Agent im Headless-Modus — dafür braucht er einen **Secret-Key**.

## 1. Secret-Key bei playit.gg holen

1. Auf <https://playit.gg> ein (kostenloses) Konto anlegen.
2. Einen **Agent** erstellen und dessen **Secret Key** kopieren
   (bei playit unter den Agent-/Docker-Einstellungen; der Key ist für genau
   solche headless/Docker-Installationen gedacht).

> Der Key ist ein Zugangsgeheimnis. Er wird nur lokal gespeichert
> (`/opt/mc-modpack-data/playit-secret`, nur für den Dienst lesbar).

## 2. Key im Panel eintragen und starten

1. Panel → Kasten **„Tunnel (playit.gg)"**.
2. Secret-Key ins Feld einfügen → **Save key**.
3. **Start tunnel**. Im Log sollte der Agent sich verbinden.

## 3. Tunnel auf playit.gg einrichten

Auf playit.gg legst du für den Agent einen **Minecraft-Java-Tunnel** an, der auf
`127.0.0.1:<dein Server-Port>` zeigt (Standard `25565`). playit gibt dir eine
**öffentliche Adresse** (z. B. `xyz.craft.playit.gg`), die deine Freunde im
Minecraft-Client unter „Server hinzufügen" eintragen.

## Hinweise

- Der Agent läuft, solange **Start tunnel** aktiv ist. **Stop** beendet ihn.
- Ohne Secret-Key startet der Agent nicht — das Panel weist dann darauf hin.
- Dieses Agent-Binary ist reiner Daemon (keine interaktive Claim-URL), daher
  der Secret-Key-Weg.
- Alternative ganz ohne Drittanbieter: Freunde ins **Tailnet** einladen
  (siehe [tailscale.md](tailscale.md)) oder Port `25565` am Router weiterleiten.
- playit.gg ist ein externer Dienst; der Datenverkehr läuft über deren Server.
