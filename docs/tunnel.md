# Tunnel für Freunde (playit.gg)

Mit einem Tunnel können Freunde beitreten, **ohne** dass du am Router einen
Port freigibst und ohne Tailscale bei den Freunden. Das Panel nutzt dafür den
kostenlosen **playit.gg**-Agent.

## So geht's

1. Panel → Kasten **„Tunnel (playit.gg)"** → **Start tunnel**.
   Beim ersten Start lädt das Panel den Agent herunter.
2. Im Tunnel-Log erscheint eine **Claim-URL** (`https://playit.gg/claim/...`).
   Diese im Browser öffnen und mit einem (kostenlosen) playit.gg-Konto verknüpfen.
3. Auf playit.gg einen **Minecraft-Java-Tunnel** anlegen, der auf
   `127.0.0.1:<dein Server-Port>` zeigt (Standard `25565`).
4. playit.gg gibt dir eine **öffentliche Adresse** (z. B. `xyz.craft.playit.gg`).
   Die geben deine Freunde im Minecraft-Client unter „Server hinzufügen" ein.

## Hinweise

- Der Tunnel läuft, solange **Start tunnel** aktiv ist. **Stop** beendet ihn.
- Der Agent merkt sich die Verknüpfung — nach dem ersten Einrichten startet er
  künftig ohne erneute Claim-URL.
- Alternative ohne Drittanbieter: Freunde ins **Tailnet** einladen
  (siehe [tailscale.md](tailscale.md)) oder am Router Port `25565` weiterleiten.
- playit.gg ist ein externer Dienst; der Datenverkehr läuft über deren Server.
