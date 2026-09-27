import tempfile
import unittest
from pathlib import Path

from telegram_media_sender.media_groups import attachment_name_key, scan_folder
from telegram_media_sender.weekly_plan import ItemKind, UploadMode, build_media_group_plan


class MediaGroupTests(unittest.TestCase):
    def test_partial_names_and_both_german_suffixes_form_one_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                "0013 Имя файла.ru.mp4",
                "0013 Имя файла.ru.srt",
                "0013 Имя файла.de.srt",
                "0013 Имя файла2.srt",
            ):
                (root / name).write_bytes(b"sample")
            groups, issues = scan_folder(root, "ru")
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].files), 4)
        self.assertEqual(len(groups[0].german), 2)
        self.assertEqual(issues[0].kind, "extra_subtitles")
        self.assertIn("будут отправлены все 3", issues[0].format("ru"))

    def test_partial_match_does_not_cross_different_group_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                "0013 Пример лекции.ru.mp4",
                "0014 Пример лекции.ru.srt",
                "0014 Пример лекции.de.srt",
            ):
                (root / name).write_bytes(b"sample")
            groups, issues = scan_folder(root)
        self.assertEqual([len(group.files) for group in groups], [1, 2])
        self.assertEqual(groups[0].name, "0013 Пример лекции")
        self.assertEqual(groups[1].name, "0014 Пример лекции")
        self.assertEqual(issues, [])

    def test_media_only_subtitle_only_and_video_audio_follow_numeric_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                "10 Поздняя лекция.ru.mp4",
                "2 Звук.m4a",
                "2 Видео.mp4",
                "3 Титры.ru.srt",
                "3 Титры.de.srt",
                "1 Первая лекция.mp4",
            ):
                (root / name).write_bytes(b"sample")
            groups, issues = scan_folder(root)
        self.assertEqual([group.name.split()[0] for group in groups], ["1", "2", "3", "10"])
        self.assertEqual([len(group.files) for group in groups], [1, 2, 2, 1])
        self.assertEqual({path.suffix for path in groups[1].media}, {".m4a", ".mp4"})
        self.assertEqual(groups[2].media, [])
        self.assertEqual(issues, [])

    def test_media_groups_convert_to_shared_plan_with_stable_album_units(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / "001 Лекция.mp4"
            media.write_bytes(b"video")
            subtitles = []
            for number in range(12):
                path = root / f"001 Лекция {number:02}.srt"
                path.write_bytes(b"subtitle")
                subtitles.append(path)
            from telegram_media_sender.media_groups import Group
            group = Group("001 Лекция", media=[media], russian=subtitles[:6], german=subtitles[6:])
            plan = build_media_group_plan([group], root)

        self.assertEqual(plan.mode, UploadMode.MEDIA_GROUPS)
        self.assertEqual([item.name for item in plan.items],
                         ["001 Лекция.mp4", *[path.name for path in subtitles]])
        self.assertEqual(len({item.group_key for item in plan.items}), 1)
        self.assertNotEqual(plan.items[0].operation_key, plan.items[1].operation_key)
        self.assertEqual(len({item.operation_key for item in plan.items[1:]}), 2)
        self.assertEqual(sum(item.kind is ItemKind.FILE for item in plan.items), 13)
        self.assertEqual([item.position for item in plan.items], list(range(1, 14)))

    def test_partial_names_without_number_can_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("имяфайла.ru.mp4", "имяфайла.ru.srt", "имяфайла2.srt"):
                (root / name).write_bytes(b"sample")
            groups, issues = scan_folder(root)
        self.assertEqual(len(groups), 1)
        self.assertEqual(issues, [])

    def test_odd_even_and_audio_bundles_are_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for base, media in (
                ("0001 Первый ролик", "0001 Первый ролик.ru.mp4"),
                ("0002 Второй ролик", "0002 Второй ролик.ru.mp4"),
                ("0013 Аудио", "0013 Аудио.ru.m4a"),
            ):
                (root / media).write_bytes(b"media")
                (root / f"{base}.ru.srt").write_text("ru")
                (root / f"{base}.srt").write_text("de")

            groups, issues = scan_folder(root)

        self.assertEqual([group.name for group in groups], [
            "0001 Первый ролик", "0002 Второй ролик", "0013 Аудио"
        ])
        self.assertTrue(groups[2].media[0].name.endswith(".m4a"))
        self.assertEqual(issues, [])

    def test_telegram_safe_filename_rewrite_still_matches_duplicate(self):
        local_name = "0002 Щитовидная железа и лечебные грибы.ru.mp4"
        telegram_name = "0002_Щитовидная_железа_и_лечебные_грибы_ru.mp4"
        self.assertEqual(attachment_name_key(local_name), attachment_name_key(telegram_name))

    def test_duplicate_key_keeps_extension_and_language_tokens(self):
        self.assertNotEqual(
            attachment_name_key("0002 тема.ru.mp4"),
            attachment_name_key("0002 тема.ru.srt"),
        )
        self.assertNotEqual(
            attachment_name_key("0002 тема.srt"),
            attachment_name_key("0002 тема.ru.srt"),
        )


if __name__ == "__main__":
    unittest.main()
