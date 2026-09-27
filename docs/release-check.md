# Release check · Проверка выпуска · Release-Prüfung

## Recorded checks — 2026-09-26

Version **1.1.2**, downloaded from GitHub Releases:

- ZIP SHA-256 matched the published `SHA256SUMS.txt`.
- The archive unpacked successfully.
- The downloaded executable stayed running for eight seconds on Apple Silicon, macOS 15.7.4, with a temporary empty home directory and Qt's offscreen platform, then was terminated by the check.
- The 31 automated tests passed before publication.
- Documentation previews were rendered from the application with demonstration files, without a Telegram profile or network activity.

This is a local startup check. Installation on another Mac, browser quarantine/Gatekeeper behavior and interactive operation of the downloaded app on that Mac have **not** been verified. No files were sent to Telegram.

## Current local candidate — 2026-09-27

Candidate-specific metadata and the ZIP SHA-256 are recorded in the local `candidate-report.json` beside each preview build. The report identifies the candidate, source commit, source-tree SHA-256, automated and manual checks, archive checksum and remaining acceptance gates.

The latest local candidate is an unsigned-for-distribution preview (ad hoc signature, no Developer ID or notarization), built for arm64 with a macOS 13.0 bundle minimum. The source tree is dirty, so it is not a release build. Automated tests and offline acceptance pass; a 5,000-file idle soak is running against the extracted candidate. StudyArchivePrep v1 was exercised using output from its actual exporter.

Real Telegram sends to a confirmed private group and channel, interactive UI verification of the latest candidate, second-Mac installation/update and a clean committed-source build remain outstanding. No candidate has been uploaded to Releases.

## English: check on another Mac

1. Use an Apple Silicon Mac running macOS 13 or newer. Download the ZIP through a browser from [Releases](https://github.com/popovantondev/TelegramMediaSender/releases/latest).
2. Unzip it, move the app to Applications and open it. Follow the [first-launch guide](en/README.md) if macOS blocks it; the build is not notarized.
3. With no existing sender data, confirm the profile selector is empty. Open Profiles and cancel adding a profile.
4. Choose a folder with numbered sample files. Check video-only, video plus audio, and subtitle-only bundles and their order, without sending them.
5. Check English, German and Russian after restarting. Move the window, quit and reopen it; check its position and that the bottom controls are visible.
6. Report the Mac model, macOS/app versions and any problem through [Issues](https://github.com/popovantondev/TelegramMediaSender/issues/new/choose), with personal data removed.

## Русский: проверка на другом Mac

1. На Mac с Apple Silicon и macOS 13 или новее скачайте ZIP через браузер из [Releases](https://github.com/popovantondev/TelegramMediaSender/releases/latest).
2. Распакуйте, перенесите приложение в «Программы» и откройте. При блокировке следуйте [инструкции первого запуска](ru/README.md): сборка не нотариально заверена Apple.
3. Если данных программы ещё нет, список профилей должен быть пустым. Откройте «Профили», начните добавление и отмените его.
4. Выберите папку с пронумерованными примерами. Проверьте комплекты только с видео, с видео и аудио, только с субтитрами и их порядок. Отправлять их не нужно.
5. Проверьте три языка после перезапуска. Передвиньте окно, закройте и откройте программу: положение должно сохраниться, нижние кнопки должны быть видны.
6. Укажите модель Mac, версии macOS и приложения и найденные проблемы в [Issues](https://github.com/popovantondev/TelegramMediaSender/issues/new/choose). Скройте личные данные.

Пока выполнена только локальная проверка запуска скачанного файла на macOS 15.7.4 с пустым временным хранилищем и без показа окна. Установка на другом Mac и поведение Gatekeeper ещё не проверены. Файлы в Telegram не отправлялись.

## Deutsch: Prüfung auf einem anderen Mac

1. Auf einem Apple-Silicon-Mac mit macOS 13 oder neuer die ZIP-Datei im Browser unter [Releases](https://github.com/popovantondev/TelegramMediaSender/releases/latest) herunterladen.
2. Entpacken, die App nach „Programme“ verschieben und öffnen. Bei einer Sperre die [Startanleitung](de/README.md) beachten; die App ist nicht von Apple notarisiert.
3. Ohne vorhandene App-Daten muss die Profilauswahl leer sein. „Profile“ öffnen, das Hinzufügen starten und abbrechen.
4. Einen Ordner mit nummerierten Beispieldateien auswählen. Reihenfolge und Pakete nur mit Video, mit Video und Audio sowie nur mit Untertiteln prüfen, ohne sie zu senden.
5. Alle drei Sprachen nach einem Neustart prüfen. Das Fenster verschieben, die App schließen und erneut öffnen: Position und sichtbare untere Schaltflächen prüfen.
6. Mac-Modell, macOS-/App-Version und Probleme unter [Issues](https://github.com/popovantondev/TelegramMediaSender/issues/new/choose) angeben. Persönliche Daten entfernen.

Bisher wurde nur der lokale Start der heruntergeladenen Datei unter macOS 15.7.4 mit einem leeren temporären Datenverzeichnis und ohne sichtbares Fenster geprüft. Installation auf einem anderen Mac und Gatekeeper-Verhalten sind noch nicht geprüft. Es wurden keine Dateien an Telegram gesendet.
