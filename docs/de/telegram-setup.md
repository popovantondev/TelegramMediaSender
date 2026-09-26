# Telegram verbinden

Die App verwendet Telegrams MTProto-API mit Telethon. Erstelle eigene API-Zugangsdaten für dein Telegram-Konto. Ein Bot-Token wird nicht benötigt.

## API ID und API Hash erstellen

1. Öffne [my.telegram.org](https://my.telegram.org) und melde dich mit deiner Telegram-Telefonnummer an.
2. Öffne **API development tools** und erstelle einen App-Eintrag.
3. Kopiere die numerische **api_id** und den **api_hash**. Telegram beschreibt den Ablauf im [offiziellen Leitfaden](https://core.telegram.org/api/obtaining_api_id).
4. Klicke in Telegram Media Sender auf „Profile…“ → „Hinzufügen…“, vergib einen Namen und trage Telefonnummer, API ID und API Hash ein.

Halte den API Hash geheim. Die App speichert ihn lokal im Profil. Füge ihn nicht in Chats, Issues oder Screenshots ein.

## Anmelden

1. Wähle das Profil und klicke auf „Aktualisieren“, um Chats zu laden.
2. Gib den Anmeldecode ein, den Telegram an ein bereits angemeldetes Gerät oder über eine andere für dein Konto verfügbare Methode sendet.
3. Wenn die Zwei-Schritt-Verifizierung aktiv ist, gib bei Aufforderung das Passwort ein.
4. Wähle einen Chat und prüfe den Empfänger, bevor du Dateien sendest.

Telethons [Anmeldedokumentation](https://docs.telethon.dev/en/stable/basic/signing-in.html) erklärt den Code- und optionalen Passwortablauf. Die App speichert die autorisierte Sitzung lokal, damit der Code nicht bei jedem Start erneut eingegeben werden muss. Die Sitzungsdatei enthält Autorisierungsdaten und muss geheim bleiben; siehe Telethons [Sitzungsleitfaden](https://docs.telethon.dev/en/stable/concepts/sessions.html).

## Zugriff widerrufen

Öffne in Telegram „Einstellungen → Geräte“ (die Bezeichnung kann je nach Plattform variieren) und beende die Sitzung dieser App. Wenn du das Profil nicht mehr brauchst, lösche es über „Profile…“ → „Löschen…“. Dabei werden nur Profildaten und Sitzung der neuen App entfernt; Profile der alten App, Telegram-Nachrichten und Originaldateien bleiben erhalten. Das Löschen einer lokalen Sitzung widerruft keine Kopien davon.
