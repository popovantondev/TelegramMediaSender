# Study by week

## Prepare the folders

Choose a root folder containing folders named `Неделя <number> …`. The week number determines order. Inside each week, use valid day folders named `YYYY-MM-DD`.

```text
Study Telegram/
├── Неделя 1 03.08 - 08.08/
│   ├── Week_01_Materials.zip
│   ├── 2026-08-03/
│   │   ├── 01_Аудио/Lecture 01.mp4
│   │   ├── 02_Субтитры/Lecture 01.de.srt
│   │   └── 04_Дополнительные_материалы.zip
│   └── 2026-08-04/
└── Неделя 2 10.08 - 14.08/
```

Files directly inside a week are shared week materials. Day folders can contain nested folders. Weeks sort by number, days by date, and files by natural filename order. Each day sends audio/video, every `.srt`, `03_Скриншоты.zip`, `04_Дополнительные_материалы.zip`, then other files. Every item is sent as a separate message. Supported audio and video retain Telegram playback.

Empty categories are allowed. macOS system files are excluded. Symbolic links and invalid date folders appear as scan issues and are not placed in the queue.

## Select and send

The first scan selects all found weeks, days, and week materials. Uncheck anything you do not want. A partially selected week displays a partial check. Refresh keeps choices for existing items and selects new items by default.

Choose **Check and send**, review the profile, chat, size, and nested message plan, then press **Start upload**. A week or day heading is sent only when that section has selected files.

### Import a prepared publication plan

Choose **Import publication plan…** and select a JSON file in `publication-plan-v1` format. The app validates the schema, item order and IDs, and each file's size and SHA-256 relative to the plan folder, then opens a separate preview. Confirming that preview only loads the plan into the table. Sending still requires the regular queue review and a separate **Start upload** action. Files are checked again before sending. If the plan or a file changed, the operation stops; import the current revision. The imported order, text, project ID, and revision are preserved, and send history is scoped to the profile and chat.

Before sending, the app checks the selected chat history page by page. Exact text or a matching file name and size are only hints; name and size do not verify remote file contents. You must choose what to do for each possible match. A Telegram message is never assigned to multiple plan items. Sending does not begin until history scanning finishes.

During an active queue, macOS temporarily prevents automatic idle sleep. The display may still turn off, and the assertion is released after completion, stop, or error. Telegram forum groups with topics are not supported yet: the app reports their count and will not silently send to the default topic. Before sending, the app reads the connected account's current Telegram upload limit. Each file is limited to the lower of that account limit and the app cap of 2,000,000,000 bytes; a larger file blocks the queue before sending.

## Resume and stop

The journal is stored in the app's local data folder. To resume, choose the saved queue and the same profile and chat. Sent items remain in the journal. An interrupted attempt is reconciled against the chat before it can continue. Opening the app never starts a queue automatically.

When stopping, choose **Finish the current file** or **Interrupt current transfer now**. If Telegram may have accepted the message, its result is marked uncertain and checked before resuming. If a source file changes, refresh the plan; the old fingerprint is not sent.

## Diagnostics and privacy

Open the local log from **Profiles** with **View diagnostics log…**. On Mac it is stored at `~/Library/Application Support/TelegramMediaSender/diagnostics.jsonl`; the current file and at most two rotated copies are kept. Open and review the log before sharing it with support. The app never sends it automatically.

The log contains the app version, event types, and safe counters. It excludes exception text, Telegram codes, API Hash values, sessions, message text, chat/profile/file names, and personal file paths.

## Isolated preview launch

Pass `--data-dir PATH` to the app executable when testing. Profiles, sessions, journal, and settings are created only in that folder, and old profiles are not migrated. For example, run the executable with `--data-dir /tmp/telegram-media-sender-preview-data`.
