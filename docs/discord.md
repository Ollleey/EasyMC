# Discord-Benachrichtigungen

Das Panel kann bei Server-Start/-Stopp, Crash und Spieler-Join/-Leave eine
Nachricht in einen Discord-Kanal posten — über einen **Webhook**.

## 1. Webhook in Discord erstellen

1. In Discord: Server-Einstellungen → **Integrationen** → **Webhooks** →
   **Neuer Webhook**.
2. Kanal wählen, optional Namen/Bild setzen.
3. **Webhook-URL kopieren** (sieht aus wie
   `https://discord.com/api/webhooks/123.../abc...`).

> Die URL ist ein Geheimnis — wer sie hat, kann in den Kanal posten. Sie wird
> nur lokal im Panel gespeichert.

## 2. Im Panel eintragen

1. Panel → **Settings**.
2. **Discord webhook URL** einfügen.
3. Haken **„Discord notifications"** setzen → **Save settings**.

Ab jetzt kommen Meldungen wie:

- 🟢 Server starting / ✅ Server is ready
- ➡️ Steve joined / ⬅️ Steve left
- ⏹️ Server stopped / 🔴 Server crashed

## Hinweis

Join/Leave werden aus der Server-Konsole erkannt. Manche Mods ändern die
Chat-Formatierung — in seltenen Fällen werden Join/Leave dann nicht erkannt.
Start/Stopp/Crash funktionieren immer.
