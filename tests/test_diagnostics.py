import json
import os
import tempfile
import unittest
from pathlib import Path

from telegram_media_sender.diagnostics import DiagnosticLog


class DiagnosticLogTests(unittest.TestCase):
    def test_log_allowlists_fields_and_never_records_error_text(self):
        with tempfile.TemporaryDirectory() as temp:
            log = DiagnosticLog(Path(temp))
            secret_error = RuntimeError("OTP 123456 /Users/private/student.txt private message")
            log.record("upload.failed", error=secret_error, mode="weekly_study",
                       item_count=3, chat_title="private chat", message="private text",
                       api_hash="secret", phase="uploading", error_type="private-token",
                       result="private-token")
            text = log.path.read_text(encoding="utf-8")
            row = json.loads(text)
            self.assertEqual(row["event"], "upload.failed")
            self.assertEqual(row["error_type"], "RuntimeError")
            self.assertEqual(row["details"], {"mode": "weekly_study", "item_count": 3,
                                               "phase": "uploading"})
            for private in ("123456", "/Users/private", "student.txt", "private message",
                            "private chat", "private text", "private-token", "secret"):
                self.assertNotIn(private, text)

    def test_logs_are_private_and_rotation_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = DiagnosticLog(root, max_bytes=1024, backup_count=2)
            for _ in range(30):
                log.record("queue.progress", mode="weekly_study", item_count=100)
            files = sorted(root.glob("diagnostics*.jsonl"))
            self.assertLessEqual(len(files), 3)
            self.assertTrue(all(path.stat().st_size <= 1024 for path in files))
            self.assertTrue(all(os.stat(path).st_mode & 0o777 == 0o600 for path in files))
            self.assertEqual(os.stat(root / "diagnostics.lock").st_mode & 0o777, 0o600)

    def test_invalid_event_and_unlisted_detail_are_discarded(self):
        with tempfile.TemporaryDirectory() as temp:
            log = DiagnosticLog(Path(temp))
            log.record("upload.failed\nprivate", mode="weekly_study", path="/private/path")
            row = json.loads(log.path.read_text(encoding="utf-8"))
            self.assertEqual(row["event"], "invalid_event")
            self.assertEqual(row["details"], {"mode": "weekly_study"})
            self.assertNotIn("private", log.path.read_text(encoding="utf-8"))

    def test_sensitive_looking_values_cannot_be_smuggled_through_safe_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            log = DiagnosticLog(Path(temp))
            log.record("upload.started", mode="private-api-hash-123456", item_count=4)
            row = json.loads(log.path.read_text(encoding="utf-8"))
            self.assertEqual(row["details"], {"item_count": 4})

    def test_logger_failure_does_not_raise_into_application(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = DiagnosticLog(root)
            root.chmod(0o500)
            try:
                log.record("app.started")
            finally:
                root.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
