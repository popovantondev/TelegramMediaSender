import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_media_sender.build_info import build_label


class RuntimeBuildInfoTests(unittest.TestCase):
    def test_bundled_candidate_id_is_visible_in_build_label(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "build-info.json").write_text(json.dumps({
                "version": "1.2.0", "candidate_id": "rc1-2026-09-27"
            }), encoding="utf-8")
            with patch("telegram_media_sender.build_info.sys._MEIPASS", directory, create=True):
                self.assertEqual(build_label(), "1.2.0 · rc1-2026-09-27")

    def test_source_run_has_clear_development_label(self):
        with patch("telegram_media_sender.build_info.sys._MEIPASS", None, create=True):
            self.assertEqual(build_label(), "1.2.0 · development")


if __name__ == "__main__":
    unittest.main()
