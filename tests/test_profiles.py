import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_media_sender.profiles import SenderProfileStore


class ProfileStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_root = self.root / "TelegramArchive"
        self.new_root = self.root / "TelegramMediaSender"
        self.old = SenderProfileStore(self.old_root, "ru")
        self.new = SenderProfileStore(self.new_root, "ru")

    def tearDown(self):
        self.temp.cleanup()

    def test_migration_uses_sqlite_backup_once_and_old_store_survives_deletion(self):
        profile = self.old.add("Старый профиль", "+491111", "12345", "hash")
        source = self.old.session_path(profile, self.old_root)
        with sqlite3.connect(source) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE session_data (value TEXT)")
            connection.execute("INSERT INTO session_data VALUES ('authorized')")
            connection.commit()
            old_profiles = self.old.path.read_bytes()
            self.new.migrate_from_legacy(self.old_root)
            imported = self.new.load()
            self.assertEqual([row["id"] for row in imported], [profile["id"]])
            copied = self.new.session_path(imported[0], self.new_root)
            with sqlite3.connect(copied) as check:
                self.assertEqual(check.execute("SELECT value FROM session_data").fetchone()[0], "authorized")
            self.assertEqual(self.old.path.read_bytes(), old_profiles)
            self.assertEqual(connection.execute("SELECT value FROM session_data").fetchone()[0], "authorized")

        self.new.delete(profile["id"])
        self.assertEqual(self.new.load(), [])
        self.assertFalse(copied.exists())
        self.new.migrate_from_legacy(self.old_root)
        self.assertEqual(self.new.load(), [], "A deleted profile must not reappear on restart.")
        self.assertEqual(self.old.load()[0]["id"], profile["id"])
        self.assertTrue(source.exists())

    def test_delete_rejects_symlink_and_keeps_profile(self):
        profile = self.new.add("Temporary", "+492222", "99", "hash")
        session = self.new.session_path(profile, self.new_root)
        outside = self.root / "outside.txt"
        outside.write_text("keep")
        session.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.new.delete(profile["id"])
        self.assertEqual(self.new.load()[0]["id"], profile["id"])
        self.assertEqual(outside.read_text(), "keep")

    def test_delete_failure_restores_profile_for_retry(self):
        profile = self.new.add("Temporary", "+493333", "99", "hash")
        session = self.new.session_path(profile, self.new_root)
        session.write_bytes(b"temporary")
        with patch("telegram_media_sender.profiles.shutil.rmtree", side_effect=PermissionError("read only")):
            with self.assertRaises(OSError):
                self.new.delete(profile["id"])
        self.assertEqual(self.new.load()[0]["id"], profile["id"])
        self.new.delete(profile["id"])
        self.assertEqual(self.new.load(), [])

    def test_migration_failure_does_not_mark_complete(self):
        old_file = self.old.root / "profiles.json"
        old_file.write_text("damaged")
        with self.assertRaises(ValueError):
            self.new.migrate_from_legacy(self.old_root)
        self.assertFalse(self.new.migration_marker.exists())
        old_file.write_text(json.dumps([]))
        self.new.migrate_from_legacy(self.old_root)
        self.assertTrue(self.new.migration_marker.exists())

    def test_legacy_default_is_not_imported_and_existing_synthetic_profile_is_removed(self):
        original = self.old_root / "telegram.session"
        original.write_bytes(b"old session stays untouched")
        self.new.migrate_from_legacy(self.old_root)
        self.assertEqual(self.new.load(), [])

        former_default = {"id": self.new.LEGACY_DEFAULT_ID,
                          "name": "Существующий локальный профиль", "phone": "+49123",
                          "api_id": "123", "api_hash": "secret"}
        self.new._write_profiles([former_default])
        copied_session = self.new.session_path(former_default, self.new_root)
        copied_session.write_bytes(b"new app's session stays untouched")
        self.new.remove_auto_imported_legacy_profile()
        self.new.remove_auto_imported_legacy_profile()
        self.assertEqual(self.new.load(), [])
        self.assertEqual(copied_session.read_bytes(), b"new app's session stays untouched")
        self.assertEqual(original.read_bytes(), b"old session stays untouched")


if __name__ == "__main__":
    unittest.main()
