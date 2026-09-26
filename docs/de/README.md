# Benutzerhandbuch

Telegram Media Sender sendet nummerierte Dateipakete aus einem lokalen Ordner an einen Telegram-Chat. Ein Paket kann Video, Audio und Untertitel in beliebiger Kombination enthalten. Der Chatverlauf wird nicht heruntergeladen.

## Erster Start

1. Lade die ZIP-Datei aus GitHub Releases, entpacke sie und verschiebe die App in den Ordner „Programme“.
2. Öffne die App. Die Builds sind nicht notarisiert. Wenn Gatekeeper den Start blockiert, prüfe, ob die App von der Releases-Seite dieses Projekts stammt. Wähle anschließend **Systemeinstellungen → Datenschutz & Sicherheit → Dennoch öffnen** nur, wenn du der Quelle vertraust.
3. Füge ein Profil mit deiner Telegram-Telefonnummer sowie API ID und API Hash hinzu. Die Schritte stehen in [Telegram verbinden](telegram-setup.md).
4. Gib den Telegram-Anmeldecode und, falls abgefragt, dein Passwort für die Zwei-Schritt-Verifizierung ein.
5. Lade die Chats, wähle den Zielchat und Ordner, markiere Pakete und sende sie.

## Medienpakete vorbereiten

Dateien mit derselben führenden Nummer bilden ein Paket, zum Beispiel `001 Lektion.ru.mp4`, `001 Lektion.ru.srt` und `001 Lektion.de.srt`. Die Pakete werden in numerischer Reihenfolge gesendet. Auch reine Video-, Audio- oder Untertitelpakete sind möglich. Leicht abweichende Untertitelnamen werden zugeordnet. Bei mehreren passenden Untertiteln derselben Sprache werden alle gesendet; die App zeigt vorher einen Hinweis.

Vor dem Upload vergleicht die App Dateinamen und Größen mit dem Verlauf des ausgewählten Chats. Prüfe mögliche Treffer und entscheide, ob das Paket übersprungen, erneut gesendet oder der Vorgang abgebrochen werden soll. Medien werden nacheinander gesendet, Untertitel als separate Dokumente.

## Lokale Daten

Profile und Sitzungsdateien bleiben auf diesem Mac unter `~/Library/Application Support/TelegramMediaSender/MediaGroupSender`. Ohne benanntes Profil ist die Profilauswahl zunächst leer. Benannte Profile der früheren App können einmalig übernommen werden; deren unbenanntes Standardkonto wird nicht automatisch angelegt. Die lokale Profildatei ist nur für dein macOS-Konto zugänglich; die App lädt diese Daten nicht hoch. Behandle eine `.session`-Datei wie ein Passwort: nicht weitergeben und nicht hochladen. Beende die Sitzung in Telegrams Liste aktiver Geräte, wenn du eine Kopie vermutest.

Beim ersten Start richtet sich die Sprache nach macOS, falls Deutsch, Russisch oder Englisch eingestellt ist. Wähle eine andere Sprache im Fenster und starte die App neu. Die Fensterposition wird lokal gespeichert.
