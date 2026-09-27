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

Candidate-specific metadata and the ZIP SHA-256 are recorded in the local `candidate-report.json` beside each preview build.

The latest candidate is **rc13-2026-09-27**, built from clean commit `4f66e0ddf3cef5d49101d983872d3e2dd70118bb`. Its arm64 ZIP is `previews/release-candidate-1.2.0-rc13-2026-09-27/TelegramMediaSender-1.2.0-macOS-arm64.zip`, SHA-256 `32f0855c9f75919f0b9a473bd8a82415aacdfae196bc38f40c9c2349d5bec031`. The bundle minimum is macOS 13.0. The app has an ad hoc signature only; it has no Developer ID signature or Apple notarization.

Recorded local checks for rc13: 125/125 automated tests, 12/12 offline readiness checks, ZIP integrity, strict code-signature verification, and the packaged 5,000-file scan. The extracted app completed a two-hour idle soak with 25 five-minute samples. RSS peaked during startup at 132,320 KiB; after startup it remained between 10 and 45 MiB, ending at 11,728 KiB. CPU was idle and the open-descriptor count remained 53. StudyArchivePrep v1 was exercised with actual exporter output. Both tabs and their tables were visually inspected in the packaged app. GitHub Actions passed for the source commit: [run 36304704584](https://github.com/popovantondev/TelegramMediaSender/actions/runs/36304704584).

The published GitHub release remains **1.1.2**. The 1.2.0 candidate has not been uploaded. Live Telegram acceptance in a specified private group and channel, installation/update on a second physical Mac, and a final clean release build remain outstanding. Publication still requires the owner's explicit release command.

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
