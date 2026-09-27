# Telegram Media Sender

<img src="src/telegram_media_sender/assets/app-icon.svg" width="88" alt="Telegram Media Sender icon">

**[Download for macOS](https://github.com/popovantondev/TelegramMediaSender/releases/latest)** · **[Deutsch](docs/de/README.md)** · **[Русский](docs/ru/README.md)** · **[English](docs/en/README.md)**

Apple Silicon (M1 or newer) · macOS 13+ · Latest published version: 1.1.2

**Telegram Media Sender** is a desktop app for macOS that sends ordered local media groups or weekly study materials to Telegram chats. The weekly mode scans dated folders, previews a sequential message plan, and keeps a local journal so a stopped or interrupted queue can continue later.

The interface selects German, Russian, or English from the macOS language on first launch. You can choose another language in the window; restart the app to apply it. The window position is remembered.

![Telegram Media Sender with example lecture bundles](docs/images/app-en.png)

*Application interface rendered with demonstration files. No Telegram account is connected; no files were uploaded.*

## What you can send

| Use case | Example files | Result |
| --- | --- | --- |
| Lecture recordings | `001 Introduction.mp4`, `002 Lecture.mp4` | Two bundles, sent in numeric order |
| Video and separate audio | `003 Lecture.mp4`, `003 Lecture.m4a` | One bundle with both files |
| Video with subtitles | `004 Lesson.mp4`, `004 Lesson.ru.srt`, `004 Lesson.de.srt` | One bundle with video and subtitles |
| Subtitles only | `005 Notes.ru.srt`, `005 Notes.de.srt` | One subtitle-only bundle |

## Downloads

Download the latest published Apple Silicon build for macOS 13 or later from [Releases](https://github.com/popovantondev/TelegramMediaSender/releases). The latest published version is **1.1.2**; version **1.2.0** is still undergoing acceptance checks and is not available from Releases yet. Unzip the download and move **Telegram Media Sender.app** to Applications.

The build is not notarized by Apple. Follow the first-launch instructions in the [user guide](docs/en/README.md). For local development, the packaged app is at `dist/TelegramMediaSender-1.2.0-macOS-arm64/Telegram Media Sender.app` unless `OUTPUT_DIR` is set.

## Current local preview

The latest local preview is `previews/release-candidate-1.2.0-rc13-2026-09-27/TelegramMediaSender-1.2.0-macOS-arm64/Telegram Media Sender.app`, built from commit `4f66e0ddf3cef5d49101d983872d3e2dd70118bb`. Its ZIP checksum and checks are in the adjacent `candidate-report.json`. It is a preview, not a published release. The previous design is preserved in `backups/design-before-unification-2026-09-27/source-and-design.zip`. See [the design audit](docs/ru/design-audit-2026-09-27.md) and [the release check](docs/release-check.md).

## Quick start

1. Install a release build and open **Telegram Media Sender**.
2. Create a Telegram API application and add its API ID and API Hash to a profile. Follow [Telegram connection setup](docs/en/telegram-setup.md).
3. Enter the login code Telegram sends to your account, and your two-step verification password if prompted.
4. Choose **Media groups** for numbered bundles or **Study by week** for dated study folders. Review the destination and upload plan before sending.

The app does not contain API keys or a Telegram account. Profile data and Telegram sessions are stored in the app's own folder under `~/Library/Application Support/TelegramMediaSender`. The profile selector is empty until a named profile exists. On first launch, explicitly named compatible profiles and their SQLite sessions from the earlier Telegram Archive sender are copied into this folder; the earlier app's data is preserved. The old app's unnamed default account is not added automatically. Profiles can be removed with **Profiles… → Delete…**. A session file is sensitive: anyone who obtains it may be able to access the Telegram account. Do not share it or upload it to this repository.

## Supported folder layout

Give related files the same leading number to place them in one bundle. Bundles are sent in numeric order. For example:

```text
001 Lesson.ru.mp4
001 Lesson.ru.srt
001 Lesson.de.srt
001 Lesson alternate.srt
```

Supported media: MP4, M4V, MOV, MKV, WebM, AVI, M4A, MP3, AAC, OGG, WAV, and FLAC. A bundle can also contain only media or only `.srt` subtitles. Subtitle names may differ slightly; files with the same leading number are grouped together. All matching subtitles are included, and the app warns when several files match one language. Before uploading, the app compares file names and sizes against the selected chat history and asks what to do when it finds a possible match.

The weekly mode recognizes `Неделя <number> …` folders and valid `YYYY-MM-DD` day folders. Files directly inside a week are sent as week materials. Day files are ordered as audio/video, every `.srt`, `03_Скриншоты.zip`, `04_Дополнительные_материалы.zip`, then other files. See the [weekly upload guide](docs/en/weekly-uploads.md).

## Technology

- Python 3.12+
- PySide6 / Qt for the macOS desktop interface
- Telethon for Telegram's MTProto API
- PyInstaller for standalone macOS packaging

## Build from source

On macOS with Xcode Command Line Tools and Python 3.12 installed:

```bash
git clone https://github.com/popovantondev/TelegramMediaSender.git
cd TelegramMediaSender
bash scripts/build_macos.sh
```

The app bundle is written to `dist/`. See the developer notes in [English](docs/en/development.md), [Deutsch](docs/de/development.md), or [Русский](docs/ru/development.md).

For a separate preview build, use `OUTPUT_DIR=previews/build-1.2.0 bash scripts/build_macos.sh`. The script refuses to overwrite a package folder that already exists. To isolate profiles, sessions, journal, and settings, launch the app executable with `--data-dir "$HOME/Documents/TelegramMediaSender-test-data"`.

## Functional readiness

The 2026-09-27 local audit now passes all 79 tests and all 12 additional offline acceptance checks, covering retries, visible feedback, progress/status updates and scan recovery. Real Telegram delivery has not been verified. See the [functional audit and next steps](docs/ru/functional-audit-2026-09-27.md). The approved design is unchanged.

## Documentation

- [Deutsch](docs/de/README.md) · [Telegram verbinden](docs/de/telegram-setup.md)
- [Русский](docs/ru/README.md) · [Подключение Telegram](docs/ru/telegram-setup.md)
- [English](docs/en/README.md) · [Connect Telegram](docs/en/telegram-setup.md)
- [Changelog](CHANGELOG.md)

## Feedback

[Report a bug or suggest a feature](https://github.com/popovantondev/TelegramMediaSender/issues/new/choose). You can write in English, German or Russian. Include your app version and macOS version; remove personal details from screenshots.

[Release verification and another-Mac checklist](docs/release-check.md).

## Rights and third-party software

This project has no open-source license. Public availability does not grant permission to reuse, modify, redistribute, or sell its source. The release binary may be downloaded and run for personal use. See [RIGHTS.md](RIGHTS.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
