# Changelog

## Unreleased

No unreleased changes are recorded.

## 1.2.0

- Add a weekly study upload tab with deterministic week/day scanning, checkboxes, nested plan preview, and separate one-message-per-item delivery.
- Add a durable SQLite upload journal with SHA-256 file versions, saved attempt IDs, resumable states, serialized queue ownership, and isolated `--data-dir` support.
- Add chat-history reconciliation, streaming media uploads, network/FloodWait recovery, safe stop choices, and automatic folder refresh monitoring.
- Add strict `publication-plan-v1` import with ordered preview, file size/SHA-256 validation, pre-send revalidation, and history bound to the project revision, profile, and chat.
- Add a size-limited local diagnostic log that omits message contents, secrets, profile/chat/file names, and personal paths; users can review it before sharing.
- Preserve the media-groups tab and add RU/DE/EN documentation for the weekly workflow.

## 1.1.2

- Shorten the German send-button label so it fits at the fixed window size.
- Leave the profile selector empty by default; stop importing the earlier app's unnamed default account and retire any previously auto-imported entry without deleting its session.
- Review German, Russian, and English interface text for consistent localization, localize common Telegram and file errors, and check button labels in every language.

## 1.1.1

- Restore the old 1280-pixel window width, use an 864-pixel content height so the bottom edge stays visible, and keep its last position.
- Use matching light menus and translated dialogs in German, Russian, and English.
- Add a profile manager with safe local profile/session deletion and one-time SQLite session migration from the earlier app.
- Round the icon arrowheads and use one SVG source for the app and `.icns`.
- Group files by numeric prefix in the requested order, including media-only, subtitle-only, and video-plus-audio bundles. Match partial subtitle names, include every matching subtitle, and warn when several files share a language.

## 1.1.0

- Publish the media sender as a separate macOS app with an independent bundle ID and data folder.
- Add German, Russian, and English interface and guides.
- Remember the app window position and recover gracefully when a saved position is no longer on a connected display.
- Use the refreshed Telegram arrow icon.
- Show queued groups with the same compact status badge style as other states.
