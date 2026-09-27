import tempfile
import unittest
from pathlib import Path

from telegram_media_sender.weekly_plan import (
    FileCategory, ItemKind, build_weekly_plan, scan_weekly_folder,
)


class WeeklyPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def put(self, relative, data=b"x"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_numeric_weeks_natural_files_and_all_subtitles(self):
        for name in ("2.mp4", "10.mp4", "01.de.srt", "01.srt", "01.ru.srt"):
            self.put(f"Неделя 10 курс/2026-08-03/{name}")
        self.put("Неделя_2 старт/2026-08-05/2.mp4")
        scan = scan_weekly_folder(self.root)
        self.assertEqual([w.number for w in scan.weeks], [2, 10])
        plan = build_weekly_plan(scan)
        self.assertEqual([item.text for item in plan.items if item.kind is ItemKind.TEXT],
                         ["Неделя_2 старт", "2026-08-05", "Неделя 10 курс", "2026-08-03"])
        day_items = [item for item in plan.items if item.day_key and item.kind is ItemKind.FILE]
        self.assertEqual([item.name for item in day_items], [
            "2.mp4", "2.mp4", "10.mp4", "01.de.srt", "01.ru.srt", "01.srt"
        ])

    def test_week_materials_multiple_archives_and_categories(self):
        self.put("Неделя 1 тест/a.zip")
        self.put("Неделя 1 тест/b.pdf")
        self.put("Неделя 1 тест/2026-08-03/04_Дополнительные_материалы.zip")
        self.put("Неделя 1 тест/2026-08-03/01_Аудио/Лекция 10.mp4")
        self.put("Неделя 1 тест/2026-08-03/01_Аудио/Лекция 2.mp3")
        self.put("Неделя 1 тест/2026-08-03/nested/titles.srt")
        self.put("Неделя 1 тест/2026-08-03/random.docx")
        scan = scan_weekly_folder(self.root)
        self.assertEqual(len(scan.weeks[0].week_files), 2)
        by_name = {f.name: f.category for d in scan.weeks[0].days for f in d.files}
        self.assertEqual(by_name["Лекция 2.mp3"], FileCategory.AUDIO_VIDEO)
        self.assertEqual(by_name["titles.srt"], FileCategory.SUBTITLES)
        self.assertEqual(by_name["04_Дополнительные_материалы.zip"], FileCategory.EXTRA_MATERIALS)
        self.assertEqual(by_name["random.docx"], FileCategory.OTHER)
        self.assertEqual(len({f.relative_path for d in scan.weeks[0].days for f in d.files}),
                         sum(len(d.files) for d in scan.weeks[0].days))

    def test_partial_selection_and_header_suppression(self):
        self.put("Неделя 1 тест/one.zip")
        self.put("Неделя 1 тест/2026-08-03/a.mp4")
        self.put("Неделя 1 тест/2026-08-04/b.srt")
        scan = scan_weekly_folder(self.root)
        week = scan.weeks[0]
        plan = build_weekly_plan(scan, {week.key}, {week.days[1].key}, set())
        self.assertEqual([i.name for i in plan.items if i.kind is ItemKind.FILE], ["b.srt"])
        self.assertEqual([i.text for i in plan.items if i.kind is ItemKind.TEXT], [week.name, "2026-08-04"])
        empty = build_weekly_plan(scan, set(), set(), set())
        self.assertEqual(empty.items, ())

    def test_invalid_dates_unrecognized_folders_and_unplaced_files_are_not_guessed(self):
        self.put("loose.txt")
        self.put("Неделя 1 тест/2026-02-30/a.mp4")
        scan = scan_weekly_folder(self.root)
        self.assertEqual(len(scan.weeks), 1)
        self.assertEqual(scan.weeks[0].days, ())
        self.assertTrue(any("YYYY-MM-DD" in notice.message for notice in scan.notices))
        self.assertTrue(any("Неделя" in notice.message for notice in scan.notices))
        plan = build_weekly_plan(scan)
        self.assertNotIn("a.mp4", [i.name for i in plan.items if i.kind is ItemKind.FILE])

    def test_system_and_hidden_files_are_excluded(self):
        self.put("Неделя 1 тест/2026-08-03/.DS_Store")
        self.put("Неделя 1 тест/2026-08-03/._resource")
        self.put("Неделя 1 тест/2026-08-03/.private.txt")
        self.put("Неделя 1 тест/2026-08-03/__MACOSX/.hidden")
        self.put("Неделя 1 тест/2026-08-03/visible.mp4")
        scan = scan_weekly_folder(self.root)
        self.assertEqual([f.name for f in scan.weeks[0].days[0].files], ["visible.mp4"])
        self.assertEqual(len(scan.excluded), 1)

    def test_missing_root_is_blocking(self):
        result = scan_weekly_folder(self.root / "absent")
        self.assertTrue(result.notices[0].blocking)


if __name__ == "__main__":
    unittest.main()
