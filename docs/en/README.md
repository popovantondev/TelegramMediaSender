# User guide

**[Download for macOS](https://github.com/popovantondev/TelegramMediaSender/releases/latest)** · [Deutsch](../de/README.md) · [Русский](../ru/README.md) · [English](../en/README.md)

![Telegram Media Sender](../images/app-en.png)

*Application interface with demonstration files; no Telegram account is connected.*

Telegram Media Sender sends numbered bundles of local files to a Telegram chat. A bundle can contain video, audio, subtitles, or any combination of them. It does not download archive history.

## First launch

1. Download the ZIP from GitHub Releases, unzip it, and move the app to Applications.
2. Open the app. Builds are not notarized. If Gatekeeper blocks a build, verify that it came from this project's Releases page, then use **System Settings → Privacy & Security → Open Anyway** only if you trust it.
3. Add a profile with the phone number, API ID, and API Hash for your own Telegram account. See [Telegram setup](telegram-setup.md).
4. Enter the code sent by Telegram and, if requested, your two-step verification password.
5. Load chats, select a destination, choose the folder, select groups, and send.

## Prepare media groups

Files with the same leading number form a bundle, for example `001 Lesson.ru.mp4`, `001 Lesson.ru.srt`, and `001 Lesson.de.srt`. Bundles are sent in numeric order. Video-only, audio-only, and subtitle-only bundles also work. Slightly different subtitle names can match. When several subtitles of one language match, all are included and the app warns before sending.

Before upload, the app checks the chosen chat for files with matching names and sizes. Review the matches and choose whether to skip them, send anyway, or cancel. Media files are sent in sequence; subtitles are sent as separate documents.

## Local data and privacy

Profiles and session files stay on this Mac under `~/Library/Application Support/TelegramMediaSender/MediaGroupSender`. The selector starts empty until a named profile exists. Named profiles from the earlier app can be imported once; its unnamed default account is not added automatically. Profile values are stored in a local file with macOS account-only permissions; the app does not upload them. Treat a `.session` file as a password: do not share, email, or upload it. Use Telegram's active sessions settings to revoke a session if you suspect it was copied.

## Languages and window

The first launch follows the macOS language when it is German, Russian, or English. Select another language in the app and restart to apply it. The window position is saved locally.
