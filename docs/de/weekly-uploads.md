# Lernen nach Wochen

## Ordner vorbereiten

Wählen Sie einen Stammordner mit Unterordnern nach dem Muster `Неделя <Nummer> …`. Die Wochennummer bestimmt die Reihenfolge. Tagesordner müssen gültige Daten im Format `YYYY-MM-DD` haben.

```text
Studium Telegram/
├── Неделя 1 03.08 - 08.08/
│   ├── Wochenmaterialien.zip
│   ├── 2026-08-03/
│   │   ├── 01_Аудио/Vorlesung 01.mp4
│   │   ├── 02_Субтитры/Vorlesung 01.de.srt
│   │   └── 04_Дополнительные_материалы.zip
│   └── 2026-08-04/
└── Неделя 2 10.08 - 14.08/
```

Dateien direkt im Wochenordner gelten als Wochenmaterialien. Tagesordner dürfen weitere Unterordner enthalten. Wochen werden nach Nummer, Tage nach Datum und Dateien natürlich nach Namen sortiert. Pro Tag kommen Audio/Video, alle `.srt`, `03_Скриншоты.zip`, `04_Дополнительные_материалы.zip` und danach sonstige Dateien. Jedes Element wird als einzelne Nachricht gesendet. Unterstützte Audio- und Videodateien bleiben in Telegram abspielbar.

Leere Kategorien sind erlaubt. macOS-Systemdateien werden ausgeschlossen. Symbolische Links und ungültige Datumsordner erscheinen als Scanprobleme und kommen nicht in die Warteschlange.

## Auswählen und senden

Beim ersten Scan werden alle gefundenen Wochen, Tage und Wochenmaterialien ausgewählt. Entfernen Sie Häkchen bei nicht gewünschten Inhalten. Eine teilweise ausgewählte Woche zeigt ein Zwischenhäkchen. Beim Aktualisieren bleibt die Auswahl für bestehende Elemente erhalten; neue Elemente werden automatisch markiert.

Klicken Sie auf **Prüfen und senden**, kontrollieren Sie Profil, Chat, Umfang und die verschachtelte Nachrichtenreihenfolge und bestätigen Sie anschließend mit **Upload starten**. Wochen- und Tagesüberschriften werden nur mit ausgewählten Dateien gesendet.

### Fertigen Veröffentlichungsplan importieren

Wählen Sie **Veröffentlichungsplan importieren…** und öffnen Sie eine JSON-Datei im Format `publication-plan-v1`. Die App prüft Schema, Reihenfolge, IDs sowie Dateigröße und SHA-256 relativ zum Planordner und zeigt danach eine separate Vorschau. Das Bestätigen der Vorschau lädt den Plan nur in die Tabelle. Gesendet wird erst nach der normalen Warteschlangenprüfung und einem separaten Klick auf **Upload starten**. Vor dem Senden werden Dateien erneut geprüft. Bei Änderungen wird der Vorgang angehalten; importieren Sie die aktuelle Revision erneut. Reihenfolge, Text, Projekt-ID und Revision bleiben erhalten. Der Verlauf wird an Profil und Chat gebunden.

Vor dem Senden prüft die App den Chatverlauf seitenweise. Exakter Text oder übereinstimmender Dateiname und Größe sind nur Hinweise; Name und Größe bestätigen nicht den entfernten Dateiinhalt. Für jeden möglichen Treffer muss eine Aktion gewählt werden. Eine Telegram-Nachricht wird höchstens einem Planelement zugeordnet. Der Versand beginnt erst nach Abschluss der Prüfung.

Während einer aktiven Warteschlange verhindert macOS vorübergehend den automatischen Ruhezustand. Der Bildschirm darf sich weiterhin ausschalten; nach Abschluss, Stopp oder Fehler wird die Sperre aufgehoben. Telegram-Forengruppen mit Themen werden noch nicht unterstützt: Die App zeigt ihre Anzahl an und sendet nicht unbemerkt im Standardthema. Vor dem Versand liest die App das aktuelle Uploadlimit des verbundenen Telegram-Kontos. Pro Datei gilt der niedrigere Wert aus Kontolimit und App-Grenze von 2.000.000.000 Byte. Größere Dateien blockieren die Warteschlange vor dem Versand.

## Fortsetzen und stoppen

Das Journal liegt im lokalen App-Datenordner. Zum Fortsetzen wählen Sie die gespeicherte Warteschlange sowie dasselbe Profil und denselben Chat. Gesendete Elemente bleiben gespeichert; ein unterbrochener Versuch wird vor dem Fortsetzen mit dem Chatverlauf abgeglichen. Beim Programmstart wird nichts automatisch gesendet.

Beim Stoppen können Sie **Aktuelle Datei fertig senden** oder **Aktuelle Übertragung sofort abbrechen** wählen. Wenn Telegram die Nachricht bereits angenommen haben könnte, wird das Ergebnis als unklar markiert und vor dem Fortsetzen geprüft. Wurde eine Quelldatei geändert, aktualisieren Sie den Plan; der alte Dateifingerabdruck wird nicht gesendet.

## Isolierter Vorschau-Start

Übergeben Sie der Programmdatei beim Testen `--data-dir PATH`. Profile, Sitzungen, Journal und Einstellungen werden nur in diesem Ordner gespeichert; alte Profile werden nicht übernommen. Beispiel: Starten Sie die Programmdatei mit `--data-dir /tmp/telegram-media-sender-preview-data`.
