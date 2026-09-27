import tempfile
import unittest
import json
import sqlite3
import os
from dataclasses import replace
from pathlib import Path

from telegram_media_sender.weekly_journal import (
    FileChangedError, QueueBusyError, WeeklyJournal, _deserialize_plan, _serialize_plan,
)
from telegram_media_sender.weekly_plan import ItemKind, UploadMode, WeeklyPlanItem, WeeklyUploadPlan


class WeeklyJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "app-data"
        self.file = self.root / "lesson.mp4"
        self.file.write_bytes(b"video data")
        self.journal = WeeklyJournal(self.data)
        self.plan = WeeklyUploadPlan((WeeklyPlanItem(
            "file:lesson.mp4", ItemKind.FILE, "week:1", "day:1", None,
            path=self.file, relative_path="lesson.mp4", name="lesson.mp4",
            size=self.file.stat().st_size, mtime_ns=self.file.stat().st_mtime_ns, position=1,
        ),), self.root, "profile", 100, 200, "Study")

    def tearDown(self):
        self.temp.cleanup()

    def test_hash_streaming_cache_and_change_detection(self):
        first = self.journal.fingerprint(self.file, block_size=2)
        self.assertEqual(first.sha256, "a37684ccb4710846dfe2f0ec8239ee3f36b5cacc1d7c917fb20984e5fd7d3de9")
        cached = self.journal.fingerprint(self.file)
        self.assertEqual(cached, first)
        self.file.write_bytes(b"changed contents")
        updated = self.journal.fingerprint(self.file)
        self.assertNotEqual(updated.sha256, first.sha256)

    def test_attempt_persists_random_id_and_confirmation(self):
        fingerprint = self.journal.fingerprint(self.file)
        run_id = self.journal.save_plan(self.plan, {"file:lesson.mp4": fingerprint})
        item_id = self.journal.run_items(run_id)[0]["item_id"]
        attempt_id, random_id = self.journal.begin_attempt(item_id)
        self.assertGreater(random_id, 0)
        self.journal.mark_sent(item_id, attempt_id, 987)
        row = self.journal.run_items(run_id)[0]
        self.assertEqual((row["status"], row["message_id"]), ("sent", 987))

    def test_album_operation_persists_all_request_ids_and_receipts_atomically(self):
        second = self.root / "caption.srt"
        second.write_text("subtitles")
        plan = replace(self.plan, items=(
            replace(self.plan.items[0], key="sub:one", operation_key="album:one", group_key="bundle:one"),
            WeeklyPlanItem("sub:two", ItemKind.FILE, "week:1", "day:1", None,
                           path=second, relative_path=second.name, name=second.name,
                           size=second.stat().st_size, mtime_ns=second.stat().st_mtime_ns,
                           group_key="bundle:one", operation_key="album:one", position=2),
        ), mode=UploadMode.MEDIA_GROUPS)
        run_id = self.journal.save_plan(plan)
        rows = self.journal.run_items(run_id)
        started = self.journal.begin_operation([row["item_id"] for row in rows], "album:one")
        self.assertEqual(len(started), 2)
        self.assertEqual(len({random_id for _, random_id in started}), 2)
        self.journal.mark_operation_uncertain(
            [(row["item_id"], attempt_id) for row, (attempt_id, _) in zip(rows, started)], "timeout")
        retried = self.journal.begin_operation([row["item_id"] for row in rows], "album:one")
        self.assertEqual([pair[1] for pair in retried], [pair[1] for pair in started])
        self.journal.mark_operation_sent([
            (row["item_id"], attempt_id, 100 + index)
            for index, (row, (attempt_id, _)) in enumerate(zip(rows, retried))
        ])
        refreshed = self.journal.run_items(run_id)
        self.assertEqual([row["status"] for row in refreshed], ["sent", "sent"])
        self.assertEqual([row["message_id"] for row in refreshed], [100, 101])

    def test_uncertain_attempt_reuses_same_random_id_after_restart(self):
        run_id = self.journal.save_plan(self.plan)
        item_id = self.journal.run_items(run_id)[0]["item_id"]
        attempt_id, random_id = self.journal.begin_attempt(item_id)
        self.journal.mark_uncertain(item_id, attempt_id, "timeout")
        self.journal.resume_interrupted(run_id)
        _retried_attempt, reused_random_id = self.journal.begin_attempt(item_id)
        self.assertEqual(reused_random_id, random_id)

    def test_new_file_version_and_deleted_original_preserve_history(self):
        fingerprint = self.journal.fingerprint(self.file)
        run_id = self.journal.save_plan(self.plan, {"file:lesson.mp4": fingerprint})
        item_id = self.journal.run_items(run_id)[0]["item_id"]
        attempt_id, _ = self.journal.begin_attempt(item_id)
        self.journal.mark_sent(item_id, attempt_id, 9)
        original_stat = self.file.stat()
        self.file.write_bytes(b"new video!")  # same length, deliberately different bytes
        os.utime(self.file, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        changed_fp = self.journal.fingerprint(self.file, use_cache=False)
        self.assertEqual((changed_fp.size, changed_fp.mtime_ns),
                         (fingerprint.size, fingerprint.mtime_ns))
        self.assertNotEqual(changed_fp.sha256, fingerprint.sha256)
        next_run = self.journal.save_plan(self.plan, {"file:lesson.mp4": changed_fp})
        self.assertNotEqual(next_run, run_id)
        rows = self.journal.run_items(next_run)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "pending")
        self.assertEqual(rows[0]["sha256"], changed_fp.sha256)
        self.assertEqual(self.journal.run_items(run_id)[0]["message_id"], 9)
        self.file.unlink()
        self.assertEqual(self.journal.run_items(run_id)[0]["message_id"], 9)

    def test_executor_lock_rejects_second_owner(self):
        other = WeeklyJournal(self.data)
        with self.journal.executor_lock():
            with self.assertRaises(QueueBusyError):
                with other.executor_lock():
                    pass

    def test_journal_stays_in_explicit_data_directory(self):
        self.assertEqual(self.journal.path, self.data.resolve() / "weekly_uploads.sqlite3")
        self.assertFalse((self.root / "weekly_uploads.sqlite3").exists())

    def test_unfinished_plan_restores_exact_snapshot_without_starting_it(self):
        run_id = self.journal.save_plan(self.plan)
        self.journal.set_run_state(run_id, "paused")
        saved = self.journal.latest_unfinished_plan()
        self.assertEqual(saved["run_id"], run_id)
        self.assertEqual(saved["state"], "paused")
        self.assertEqual(saved["plan"], self.plan)
        self.assertEqual(saved["pending"], 1)

    def test_different_plan_snapshot_gets_its_own_saved_queue(self):
        first_run = self.journal.save_plan(self.plan)
        self.journal.set_run_state(first_run, "paused")
        changed = replace(self.plan, chat_title="A different display name")
        second_run = self.journal.save_plan(changed)
        self.assertNotEqual(first_run, second_run)
        self.assertEqual(self.journal.latest_unfinished_plan()["run_id"], second_run)

    def test_old_weekly_snapshot_round_trips_without_changing_its_identity(self):
        legacy = json.dumps({
            "root": str(self.root), "profile_id": "profile", "account_id": 100,
            "chat_id": 200, "chat_title": "Study", "publication_project_id": "",
            "publication_revision": None,
            "items": [{
                "key": "file:lesson.mp4", "kind": "file", "week_key": "week:1",
                "day_key": "day:1", "category": None, "text": None,
                "path": str(self.file), "relative_path": "lesson.mp4", "name": "lesson.mp4",
                "size": self.file.stat().st_size, "mtime_ns": self.file.stat().st_mtime_ns,
                "sha256": None, "position": 1,
            }],
        }, ensure_ascii=False, separators=(",", ":"))
        restored = _deserialize_plan(legacy)
        self.assertEqual(restored.mode, UploadMode.WEEKLY_STUDY)
        self.assertEqual(_serialize_plan(restored), legacy)

    def test_media_plan_snapshot_keeps_mode_group_and_operation_keys(self):
        media_item = replace(self.plan.items[0], group_key="bundle:lesson.mp4",
                             operation_key="bundle:lesson.mp4:media:0")
        media_plan = replace(self.plan, items=(media_item,), mode=UploadMode.MEDIA_GROUPS)
        restored = _deserialize_plan(_serialize_plan(media_plan))
        self.assertEqual(restored.mode, UploadMode.MEDIA_GROUPS)
        self.assertEqual(restored.items[0].group_key, media_item.group_key)
        self.assertEqual(restored.items[0].operation_key, media_item.operation_key)

    def test_v1_database_migrates_atomically_and_keeps_a_restorable_backup(self):
        legacy_data = self.root / "legacy-app-data"
        legacy_data.mkdir()
        database = legacy_data / "weekly_uploads.sqlite3"
        connection = sqlite3.connect(database)
        connection.executescript("""
            CREATE TABLE runs (
                run_id INTEGER PRIMARY KEY, profile_id TEXT NOT NULL, account_id INTEGER,
                chat_id TEXT NOT NULL, chat_title TEXT NOT NULL, root_path TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, state TEXT NOT NULL,
                plan_json TEXT NOT NULL
            );
            CREATE TABLE items (
                item_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(run_id),
                item_key TEXT NOT NULL, position INTEGER NOT NULL, kind TEXT NOT NULL,
                week_key TEXT NOT NULL, day_key TEXT, category TEXT, relative_path TEXT,
                text_content TEXT, file_name TEXT, file_size INTEGER NOT NULL DEFAULT 0,
                mtime_ns INTEGER NOT NULL DEFAULT 0, sha256 TEXT, status TEXT NOT NULL,
                message_id INTEGER, error TEXT, uncertain INTEGER NOT NULL DEFAULT 0,
                UNIQUE(run_id,item_key,file_size,mtime_ns,sha256)
            );
            CREATE INDEX items_run_status ON items(run_id,status,position);
            CREATE TABLE attempts (
                attempt_id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(item_id),
                attempt_no INTEGER NOT NULL, random_id INTEGER NOT NULL, started_at REAL NOT NULL,
                finished_at REAL, result TEXT NOT NULL, message_id INTEGER, error TEXT,
                UNIQUE(item_id,attempt_no), UNIQUE(random_id)
            );
            CREATE TABLE fingerprint_cache (
                path TEXT NOT NULL, file_size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                sha256 TEXT NOT NULL, PRIMARY KEY(path,file_size,mtime_ns)
            );
            PRAGMA user_version=1;
        """)
        connection.execute("""INSERT INTO runs VALUES(1,?,?,?,?,?,?,?,?,?)""",
                           ("profile", 100, "200", "Study", str(self.root),
                            1.0, 2.0, "paused", _serialize_plan(self.plan)))
        connection.execute("""INSERT INTO items(
            item_id,run_id,item_key,position,kind,week_key,day_key,relative_path,file_name,
            file_size,mtime_ns,status) VALUES(1,1,?,1,'file','week:1','day:1',?,?,?,?,'sent')""",
                           ("file:lesson.mp4", "lesson.mp4", "lesson.mp4",
                            self.file.stat().st_size, self.file.stat().st_mtime_ns))
        connection.commit()
        connection.close()

        migrated = WeeklyJournal(legacy_data)
        with migrated._connect() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(items)")}
        self.assertTrue({"group_key", "operation_key"} <= columns)
        with migrated._connect() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT mode FROM runs WHERE run_id=1").fetchone()["mode"],
                             "weekly_study")
            self.assertEqual(db.execute("SELECT status FROM items WHERE item_id=1").fetchone()["status"],
                             "sent")
        saved = migrated.latest_unfinished_plan()
        self.assertEqual(saved["plan"], self.plan)
        backup_paths = list(legacy_data.glob("weekly_uploads-v1-backup-*.sqlite3"))
        self.assertEqual(len(backup_paths), 1)
        with sqlite3.connect(backup_paths[0]) as backup:
            self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(backup.execute("SELECT state FROM runs WHERE run_id=1").fetchone()[0],
                             "paused")

    def test_failed_v1_migration_rolls_back_schema_and_keeps_backup(self):
        legacy_data = self.root / "broken-legacy-data"
        legacy_data.mkdir()
        database = legacy_data / "weekly_uploads.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA user_version=1")
        with self.assertRaises(sqlite3.OperationalError):
            WeeklyJournal(legacy_data)
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA table_info(runs)").fetchall(), [])
        backups = list(legacy_data.glob("weekly_uploads-v1-backup-*.sqlite3"))
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as backup:
            self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
