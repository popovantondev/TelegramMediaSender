import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BuildInfoTests(unittest.TestCase):
    def test_build_metadata_identifies_commit_candidate_and_source_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "build-info.json"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/write_build_info.py"),
                 "--output", str(output), "--candidate", "test-candidate-7"],
                cwd=ROOT, check=True,
            )
            info = json.loads(output.read_text(encoding="utf-8"))

        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
        self.assertEqual(info["source_commit"], commit)
        self.assertEqual(info["candidate_id"], "test-candidate-7")
        self.assertRegex(info["source_tree_sha256"], r"^[0-9a-f]{64}$")
        self.assertIsInstance(info["source_tree_dirty"], bool)
        self.assertEqual(info["version"], "1.2.0")
        self.assertIn("PySide6==6.10.2", info["build_environment_packages"])
        self.assertIn("Telethon==1.42.0", info["build_environment_packages"])
        self.assertEqual(len(info["build_environment_packages"]), len(set(info["build_environment_packages"])))
        self.assertTrue(all("/Users/" not in package for package in info["build_environment_packages"]))


if __name__ == "__main__":
    unittest.main()
