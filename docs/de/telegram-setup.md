# Telegram verbinden

Die App verwendet Telegrams MTProto-API mit Telethon. Erstellen Sie eigene API-Zugangsdaten für Ihr Telegram-Konto. Ein Bot-Token wird nicht benötigt.

## API ID und API Hash erstellen

1. Öffnen Sie [my.telegram.org](https://my.telegram.org) und melden Sie sich mit Ihrer Telegram-Telefonnummer an.
2. Öffnen Sie **API development tools** und erstellen Sie einen App-Eintrag.
3. Kopieren Sie die numerische **api_id** und den **api_hash**. Telegram beschreibt den Ablauf im [offiziellen Leitfaden](https://core.telegram.org/api/obtaining_api_id).
4. Klicken Sie in Telegram Media Sender auf „Profile…“ → „Hinzufügen…“, vergeben Sie einen Namen und tragen Sie Telefonnummer, API ID und API Hash ein.

Halten Sie den API Hash geheim. Die App speichert ihn lokal im Profil. Fügen Sie ihn nicht in Chats, Issues oder Screenshots ein.

## Anmelden

1. Wählen Sie das Profil und klicken Sie auf „Aktualisieren“, um Chats zu laden.
2. Geben Sie den Anmeldecode ein, den Telegram an ein bereits angemeldetes Gerät oder über eine andere für Ihr Konto verfügbare Methode sendet.
3. Wenn die Zwei-Schritt-Verifizierung aktiv ist, geben Sie bei Aufforderung das Passwort ein.
4. Wählen Sie einen Chat und prüfen Sie den Empfänger, bevor Sie Dateien senden.

Telethons [Anmeldedokumentation](https://docs.telethon.dev/en/stable/basic/signing-in.html) erklärt den Code- und optionalen Passwortablauf. Die App speichert die autorisierte Sitzung lokal, damit der Code nicht bei jedem Start erneut eingegeben werden muss. Die Sitzungsdatei enthält Autorisierungsdaten und muss geheim bleiben; siehe Telethons [Sitzungsleitfaden](https://docs.telethon.dev/en/stable/concepts/sessions.html).

## Zugriff widerrufen

Öffnen Sie in Telegram „Einstellungen → Geräte“ (die Bezeichnung kann je nach Plattform variieren) und beenden Sie die Sitzung dieser App. Wenn Sie das Profil nicht mehr brauchen, löschen Sie es über „Profile…“ → „Löschen…“. Dabei werden nur Profildaten und Sitzung der neuen App entfernt; Profile der alten App, Telegram-Nachrichten und Originaldateien bleiben erhalten. Das Löschen einer lokalen Sitzung widerruft keine Kopien davon.
