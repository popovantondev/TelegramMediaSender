import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from telegram_media_sender.publication_plan_import import (
    PublicationPlanImportError,
    load_publication_plan,
    revalidate_publication_item,
)
from telegram_media_sender.weekly_plan import ItemKind


class PublicationPlanImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.materials = self.root / "Неделя 1" / "2026-08-03"
        self.materials.mkdir(parents=True)
        self.file = self.materials / "Лекция 01.mp4"
        self.file.write_bytes(b"synthetic media")
        self.manifest_path = self.root / "publication-plan.json"
        self.project_id = "00000000-0000-4000-8000-000000000001"
        self.text_id = "00000000-0000-4000-8000-000000000002"
        self.file_id = "00000000-0000-4000-8000-000000000003"
        self.data = {
            "format": "study-archive-publication-plan",
            "schema_version": 1,
            "project_id": self.project_id,
            "revision": 7,
            "items": [
                {"id": self.text_id, "kind": "text", "week": 1,
                 "date": "2026-08-03", "text": "Точный заголовок\nбез нормализации"},
                {"id": self.file_id, "kind": "file", "week": 1,
                 "date": "2026-08-03", "path": "Неделя 1/2026-08-03/Лекция 01.mp4",
                 "name": "Лекция 01.mp4", "size": self.file.stat().st_size,
                 "sha256": hashlib.sha256(self.file.read_bytes()).hexdigest()},
            ],
        }
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, data=None):
        self.manifest_path.write_text(json.dumps(self.data if data is None else data,
                                                 ensure_ascii=False), encoding="utf-8")

    def test_import_preserves_item_order_text_ids_and_revision(self):
        plan = load_publication_plan(self.manifest_path)
        self.assertEqual([item.key for item in plan.items], [self.text_id, self.file_id])
        self.assertEqual([item.position for item in plan.items], [0, 1])
        self.assertEqual(plan.items[0].text, "Точный заголовок\nбез нормализации")
        self.assertIs(plan.items[0].kind, ItemKind.TEXT)
        self.assertEqual(plan.items[1].relative_path, self.data["items"][1]["path"])
        self.assertEqual(plan.items[1].sha256, self.data["items"][1]["sha256"])
        self.assertEqual((plan.publication_project_id, plan.publication_revision),
                         (self.project_id, 7))
        self.assertEqual(plan.items[1].path, self.file.resolve())

    def test_study_archive_prep_export_fixture_imports_in_exact_order(self):
        fixture = (Path(__file__).parent / "fixtures"
                   / "study_archive_prep_publication_plan_v1")
        manifest_path = fixture / "publication-plan.json"
        exported = json.loads(manifest_path.read_text(encoding="utf-8"))

        plan = load_publication_plan(manifest_path)

        self.assertEqual(plan.publication_project_id, exported["project_id"])
        self.assertEqual(plan.publication_revision, exported["revision"])
        self.assertEqual([item.key for item in plan.items],
                         [entry["id"] for entry in exported["items"]])
        self.assertEqual([item.position for item in plan.items],
                         list(range(len(exported["items"]))))
        self.assertEqual([item.kind for item in plan.items], [
            ItemKind.TEXT, ItemKind.TEXT, ItemKind.FILE, ItemKind.FILE,
            ItemKind.FILE, ItemKind.FILE, ItemKind.FILE, ItemKind.TEXT,
        ])
        self.assertEqual([item.text for item in plan.items if item.kind is ItemKind.TEXT], [
            "Неделя 1 03.08 - 03.08", "2026-08-03", "Дополнительная заметка",
        ])
        self.assertEqual([item.name for item in plan.items if item.kind is ItemKind.FILE], [
            "lecture.mkv", "lecture.ru.srt", "lecture.srt",
            "03_Скриншоты.zip", "04_Дополнительные_материалы.zip",
        ])
        for item, entry in zip(plan.items, exported["items"]):
            if item.kind is ItemKind.FILE:
                self.assertEqual(item.relative_path, entry["path"])
                self.assertEqual(item.size, entry["size"])
                self.assertEqual(item.sha256, entry["sha256"])
                self.assertTrue(item.path.is_relative_to(fixture.resolve()))

    def test_unknown_version_and_unknown_fields_fail_closed(self):
        invalid = dict(self.data, schema_version=2)
        self.write(invalid)
        with self.assertRaises(PublicationPlanImportError):
            load_publication_plan(self.manifest_path)
        invalid = dict(self.data, secret="not allowed")
        self.write(invalid)
        with self.assertRaises(PublicationPlanImportError):
            load_publication_plan(self.manifest_path)

    def test_duplicate_json_keys_are_rejected(self):
        self.manifest_path.write_text('{"format":"study-archive-publication-plan",'
                                      '"format":"study-archive-publication-plan"}', encoding="utf-8")
        with self.assertRaisesRegex(PublicationPlanImportError, "duplicate JSON key"):
            load_publication_plan(self.manifest_path)

    def test_bad_file_size_or_digest_is_rejected(self):
        for field, value in (("size", 999), ("sha256", "0" * 64)):
            invalid = json.loads(json.dumps(self.data))
            invalid["items"][1][field] = value
            self.write(invalid)
            with self.subTest(field=field), self.assertRaises(PublicationPlanImportError):
                load_publication_plan(self.manifest_path)

    def test_absolute_parent_and_backslash_paths_are_rejected(self):
        for unsafe in ("../outside.bin", str(self.file), "Неделя 1\\file.mp4"):
            invalid = json.loads(json.dumps(self.data))
            invalid["items"][1]["path"] = unsafe
            invalid["items"][1]["name"] = Path(unsafe).name
            self.write(invalid)
            with self.subTest(path=unsafe), self.assertRaises(PublicationPlanImportError):
                load_publication_plan(self.manifest_path)

    def test_symlink_component_is_rejected(self):
        link = self.root / "alias"
        link.symlink_to(self.materials, target_is_directory=True)
        invalid = json.loads(json.dumps(self.data))
        invalid["items"][1]["path"] = "alias/Лекция 01.mp4"
        invalid["items"][1]["name"] = "Лекция 01.mp4"
        self.write(invalid)
        with self.assertRaises(PublicationPlanImportError):
            load_publication_plan(self.manifest_path)

    def test_revalidation_detects_same_size_changed_content(self):
        plan = load_publication_plan(self.manifest_path)
        self.file.write_bytes(b"synthetix media")
        self.assertEqual(self.file.stat().st_size, plan.items[1].size)
        with self.assertRaisesRegex(PublicationPlanImportError, "changed after preview"):
            revalidate_publication_item(plan.root, plan.items[1].relative_path,
                                        plan.items[1].size, plan.items[1].sha256)


if __name__ == "__main__":
    unittest.main()
