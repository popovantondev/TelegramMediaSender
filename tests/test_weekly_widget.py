import tempfile
import unittest
import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from telegram_media_sender.weekly_widget import WeeklyStudyWidget, _CheckboxDelegate, _file_count
from telegram_media_sender.weekly_journal import WeeklyJournal


class WeeklyStudyWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / "Учеба"
        (self.folder / "Неделя 1" / "2026-08-03").mkdir(parents=True)
        (self.folder / "Неделя 1" / "2026-08-03" / "Лекция 1.mp4").write_bytes(b"media")
        (self.folder / "Неделя 1" / "2026-08-04").mkdir()
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        self.settings.setValue("weekly/root", str(self.folder))
        self.widget = WeeklyStudyWidget("ru", self.settings)
        self._wait_scan()

    def tearDown(self):
        if self.widget._scan_thread and self.widget._scan_thread.isRunning():
            self.widget._scan_thread.wait(2000)
        self.widget.close()
        self.temp.cleanup()

    def _wait_scan(self):
        thread = self.widget._scan_thread
        if thread:
            thread.wait(2000)
        self.app.processEvents()

    def test_first_scan_selects_available_week_and_day(self):
        self.assertEqual(len(self.widget.week_checks), 1)
        self.assertEqual(len(self.widget.day_checks), 2)
        self.assertTrue(self.widget.selected_plan().items)

    def test_scan_and_render_five_thousand_files_without_losing_rows(self):
        from telegram_media_sender.weekly_plan import scan_weekly_folder
        large_root = self.root / "large-set"
        day = large_root / "Неделя 1" / "2026-08-03"
        day.mkdir(parents=True)
        for index in range(5000):
            (day / f"Материал {index:05}.bin").write_bytes(b"x")
        scan = scan_weekly_folder(large_root)
        self.widget.scan = scan
        self.widget.week_checks = {week.key for week in scan.weeks}
        self.widget.day_checks = {entry.key for week in scan.weeks for entry in week.days}
        self.widget.week_material_checks = set()
        self.widget._populate_tree()
        week = self.widget.tree.topLevelItem(0)
        day_node = week.child(0)
        category_node = day_node.child(0)
        self.assertEqual(category_node.childCount(), 5000)
        self.assertEqual(category_node.child(4999).text(0), "Материал 04999.bin")

    def test_send_stays_disabled_until_profile_and_chat_are_ready(self):
        self.assertFalse(self.widget.send_button.isEnabled())
        self.widget.set_target_ready(True)
        self.assertTrue(self.widget.send_button.isEnabled())
        self.widget.set_target_ready(False)
        self.assertFalse(self.widget.send_button.isEnabled())

    def test_checked_tree_box_paints_a_visible_tick(self):
        tree = QTreeWidget()
        tree.setColumnCount(1)
        tree.setStyleSheet("QTreeWidget::indicator { width: 22px; height: 22px; "
                           "border: 1px solid #aebfd3; border-radius: 4px; background: #fff } "
                           "QTreeWidget::indicator:checked { border-color: #1684e8; "
                           "background: #1684e8 }")
        item = QTreeWidgetItem(tree, ["Selected"])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked)
        tree.setItemDelegate(_CheckboxDelegate(tree))
        tree.resize(300, 100)
        tree.show()
        self.app.processEvents()
        image = tree.grab().toImage()
        blue = [(x, y) for y in range(image.height()) for x in range(image.width())
                if image.pixelColor(x, y).name() == "#1684e8"]
        self.assertTrue(blue, "checked indicator should use the selected blue")
        left, right = min(x for x, _ in blue), max(x for x, _ in blue)
        top, bottom = min(y for _, y in blue), max(y for _, y in blue)
        white_tick = any(image.pixelColor(x, y).name() == "#ffffff"
                         for y in range(top + 4, bottom - 3)
                         for x in range(left + 4, right - 3))
        self.assertTrue(white_tick, "checked indicator should include a white tick")
        tree.close()

    def test_russian_file_count_uses_correct_plural_forms(self):
        self.assertEqual([_file_count(n, "ru") for n in (1, 2, 5, 11, 21)],
                         ["1 файл", "2 файла", "5 файлов", "11 файлов", "21 файл"])

    def test_uploaded_item_updates_file_day_and_week_badges(self):
        file_key = self.widget.scan.weeks[0].days[0].files[0].key
        week = self.widget.tree.topLevelItem(0)
        day = week.child(0)
        self.widget.update_item_status(file_key, "sending")
        self.assertEqual(day.data(3, Qt.ItemDataRole.UserRole + 1), "sending")
        self.assertEqual(week.data(3, Qt.ItemDataRole.UserRole + 1), "sending")
        self.widget.update_item_status(file_key, "sent")
        self.widget.update_item_status("header:day:Неделя 1/2026-08-03", "sent")
        self.widget.update_item_status("header:week:Неделя 1", "sent")
        self.assertEqual(day.data(3, Qt.ItemDataRole.UserRole + 1), "sent")
        self.assertEqual(week.data(3, Qt.ItemDataRole.UserRole + 1), "sent")

    def test_item_without_files_in_selected_day_does_not_keep_week_partial(self):
        week = self.widget.tree.topLevelItem(0)
        empty_day = week.child(1)
        self.assertEqual(empty_day.data(3, Qt.ItemDataRole.UserRole + 1), "idle")
        file_key = self.widget.scan.weeks[0].days[0].files[0].key
        self.widget.update_item_status(file_key, "sent")
        self.widget.update_item_status("header:day:Неделя 1/2026-08-03", "sent")
        self.widget.update_item_status("header:week:Неделя 1", "sent")
        self.assertEqual(week.data(3, Qt.ItemDataRole.UserRole + 1), "sent")

    def test_refresh_works_again_after_folder_scan_failure(self):
        self.widget.root = self.folder
        self.widget._scan_failed("simulated access denied")
        self.assertIsNone(self.widget.scan)
        self.assertFalse(self.widget.send_button.isEnabled())
        self.assertIn("0 недель", self.widget.summary.text())
        from unittest.mock import patch
        with patch.object(self.widget, "set_root") as scan_again:
            self.widget.refresh()
        scan_again.assert_called_once_with(self.folder)

    def test_refresh_preserves_existing_choice_and_selects_new_entries(self):
        week = self.widget.scan.weeks[0]
        day = week.days[0]
        self.widget.week_checks.clear()
        self.widget.day_checks.clear()
        self.widget.refresh()
        self._wait_scan()
        self.assertNotIn(week.key, self.widget.week_checks)
        self.assertNotIn(day.key, self.widget.day_checks)
        new_day = self.folder / "Неделя 1" / "2026-08-05"
        new_day.mkdir()
        (new_day / "new.pdf").write_bytes(b"new")
        self.widget.refresh()
        self._wait_scan()
        self.assertIn("day:Неделя 1/2026-08-05", self.widget.day_checks)

    def test_refresh_button_does_not_send(self):
        emitted = []
        self.widget.plan_ready.connect(emitted.append)
        self.widget.refresh()
        self._wait_scan()
        self.assertEqual(emitted, [])

    def test_unchanged_watcher_snapshot_does_not_rescan_or_disable_folder_buttons(self):
        current_scan = self.widget.scan
        self.assertTrue(self.widget.choose_button.isEnabled())
        self.assertTrue(self.widget.refresh_button.isEnabled())
        self.widget._check_folder_change()
        self.app.processEvents()
        self.assertIs(self.widget.scan, current_scan)
        self.assertTrue(self.widget.choose_button.isEnabled())
        self.assertTrue(self.widget.refresh_button.isEnabled())

    def test_automatic_refresh_keeps_folder_buttons_enabled(self):
        self.widget.set_root(self.folder, manual=False)
        self.assertTrue(self.widget.choose_button.isEnabled())
        self.assertTrue(self.widget.refresh_button.isEnabled())
        self._wait_scan()
        self.assertTrue(self.widget.choose_button.isEnabled())
        self.assertTrue(self.widget.refresh_button.isEnabled())

    def test_watcher_only_tracks_folders_inside_the_selected_root(self):
        watched = {Path(path) for path in self.widget.watcher.directories()}
        self.assertTrue(watched)
        root = self.folder.resolve()
        self.assertTrue(all(path == root or root in path.parents for path in watched))

    def test_watcher_rescans_after_a_real_change_without_disabling_controls(self):
        new_day = self.folder / "Неделя 1" / "2026-08-05"
        new_day.mkdir()
        (new_day / "new.pdf").write_bytes(b"new")
        self.widget._folder_changed(str(new_day))
        QTest.qWait(1500)
        thread = self.widget._scan_thread
        if thread:
            thread.wait(2000)
        self.app.processEvents()
        self.assertIn("day:Неделя 1/2026-08-05", self.widget.day_checks)
        self.assertTrue(self.widget.choose_button.isEnabled())
        self.assertTrue(self.widget.refresh_button.isEnabled())

    def test_week_checkbox_shows_partial_selection_without_reselecting_children(self):
        week = self.widget.scan.weeks[0]
        top = self.widget.tree.topLevelItem(0)
        day = top.child(1)
        day.setCheckState(0, Qt.CheckState.Unchecked)
        self.app.processEvents()
        self.assertIn(week.key, self.widget.week_checks)
        self.assertNotIn(week.days[1].key, self.widget.day_checks)
        self.assertEqual(top.checkState(0), Qt.CheckState.PartiallyChecked)

    def test_saved_unfinished_queue_is_offered_without_starting_it(self):
        data_dir = self.root / "app-data"
        journal = WeeklyJournal(data_dir)
        plan = self.widget.selected_plan(profile_id="profile-1", account_id=123,
                                         chat_id=-456, chat_title="Учебная группа")
        run_id = journal.save_plan(plan)
        journal.set_run_state(run_id, "paused")
        resumed_widget = WeeklyStudyWidget("ru", self.settings, data_dir=data_dir)
        self.addCleanup(resumed_widget.close)
        if resumed_widget._scan_thread:
            resumed_widget._scan_thread.wait(2000)
            self.app.processEvents()
        self.assertFalse(resumed_widget.resume_button.isHidden())
        emitted = []
        resumed_widget.plan_ready.connect(emitted.append)
        resumed_widget.continue_saved_upload()
        self.assertEqual(emitted, [plan])
        self.assertEqual(journal.latest_unfinished_plan()["state"], "paused")

    def test_publication_plan_import_previews_and_displays_exact_order(self):
        from unittest.mock import patch
        export_root = self.root / "exported"
        file = export_root / "Материалы" / "lesson.pdf"
        file.parent.mkdir(parents=True)
        file.write_bytes(b"exported synthetic file")
        manifest_path = export_root / "publication-plan.json"
        text_id = "00000000-0000-4000-8000-000000000201"
        file_id = "00000000-0000-4000-8000-000000000202"
        manifest_path.write_text(json.dumps({
            "format": "study-archive-publication-plan", "schema_version": 1,
            "project_id": "00000000-0000-4000-8000-000000000200", "revision": 3,
            "items": [
                {"id": text_id, "kind": "text", "week": 1, "date": None,
                 "text": "Exact first message"},
                {"id": file_id, "kind": "file", "week": 1, "date": "2026-08-03",
                 "path": "Материалы/lesson.pdf", "name": "lesson.pdf",
                 "size": file.stat().st_size, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        with patch("telegram_media_sender.weekly_widget.QFileDialog.getOpenFileName",
                   return_value=(str(manifest_path), "")), \
             patch.object(self.widget, "confirm_plan", return_value=True) as preview:
            self.widget.import_publication_plan()
            thread = self.widget._import_thread
            thread.wait(3000)
            self.app.processEvents()
        preview.assert_called_once()
        self.assertEqual(preview.call_args.args[1]["import_preview"], True)
        self.assertEqual(self.widget.imported_plan.publication_project_id,
                         "00000000-0000-4000-8000-000000000200")
        self.assertEqual(self.widget.tree.topLevelItemCount(), 2)
        self.assertEqual(self.widget.tree.topLevelItem(0).text(0), "Exact first message")
        self.assertEqual(self.widget.tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole), text_id)
        self.assertEqual(self.widget.tree.topLevelItem(1).text(0), "lesson.pdf")
        self.assertEqual(self.widget.tree.topLevelItem(1).data(0, Qt.ItemDataRole.UserRole), file_id)
        self.assertTrue(self.widget.select_all_button.isHidden())
        self.widget.set_target_ready(True)
        self.assertTrue(self.widget.send_button.isEnabled())
        emitted = []
        self.widget.plan_ready.connect(emitted.append)
        self.widget.review_plan()
        self.assertEqual([item.key for item in emitted[0].items], [text_id, file_id])

    def test_final_queue_confirmation_shows_selected_profile_and_chat(self):
        from unittest.mock import patch
        plan = self.widget.selected_plan(profile_id="profile-test", account_id=123,
                                         chat_id=-456, chat_title="Private test chat")
        labels = []

        def accept_confirmation(dialog, *_args):
            labels.extend(label.text() for label in dialog.findChildren(QLabel))
            return QDialog.DialogCode.Accepted

        with patch("telegram_media_sender.weekly_widget.QDialog.exec", new=accept_confirmation):
            self.assertTrue(self.widget.confirm_plan(plan))
        self.assertTrue(any("profile-test" in label for label in labels))
        self.assertTrue(any("Private test chat" in label for label in labels))

    def test_imported_plan_final_confirmation_shows_profile_and_selected_chat(self):
        from dataclasses import replace
        from unittest.mock import patch
        from telegram_media_sender.weekly_plan import UploadMode
        plan = replace(self.widget.selected_plan(profile_id="profile-import", account_id=321,
                                                  chat_id=-654, chat_title="Import test channel"),
                       publication_project_id="project-import", publication_revision=7,
                       mode=UploadMode.PUBLICATION_PLAN)
        labels = []

        def accept_confirmation(dialog, *_args):
            labels.extend(label.text() for label in dialog.findChildren(QLabel))
            return QDialog.DialogCode.Accepted

        with patch("telegram_media_sender.weekly_widget.QDialog.exec", new=accept_confirmation):
            self.assertTrue(self.widget.confirm_plan(plan, {"pending": plan.message_count}))
        self.assertTrue(any("profile-import" in label for label in labels))
        self.assertTrue(any("Import test channel" in label for label in labels))

    def test_media_group_review_uses_group_names_and_group_count(self):
        from dataclasses import replace
        from unittest.mock import patch
        from telegram_media_sender.weekly_plan import UploadMode
        original = self.widget.selected_plan().items[-1]
        item = replace(original, week_key="group:Пакет 001", day_key=None,
                       group_key="bundle:Пакет 001", operation_key="bundle:Пакет 001:media:0")
        plan = replace(self.widget.selected_plan(profile_id="profile-media", chat_title="Media test"),
                       items=(item,), mode=UploadMode.MEDIA_GROUPS)
        labels = []
        preview_names = []

        def accept_confirmation(dialog):
            labels.extend(label.text() for label in dialog.findChildren(QLabel))
            tree = dialog.findChild(QTreeWidget, "planTree")
            preview_names.append(tree.topLevelItem(0).text(0))
            return QDialog.DialogCode.Accepted

        with patch("telegram_media_sender.weekly_widget.QDialog.exec", new=accept_confirmation):
            self.assertTrue(self.widget.confirm_plan(plan))
        self.assertTrue(any("1 комплект" in label for label in labels))
        self.assertEqual(preview_names, ["Пакет 001"])

    def test_refresh_revalidates_imported_file_before_send(self):
        from unittest.mock import patch
        export_root = self.root / "exported"
        export_root.mkdir()
        file = export_root / "lesson.bin"
        file.write_bytes(b"sample")
        manifest_path = export_root / "publication-plan.json"
        manifest_path.write_text(json.dumps({
            "format": "study-archive-publication-plan", "schema_version": 1,
            "project_id": "00000000-0000-4000-8000-000000000210", "revision": 1,
            "items": [{"id": "00000000-0000-4000-8000-000000000211", "kind": "file",
                       "week": 1, "date": None, "path": "lesson.bin", "name": "lesson.bin",
                       "size": file.stat().st_size, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}],
        }), encoding="utf-8")
        with patch("telegram_media_sender.weekly_widget.QFileDialog.getOpenFileName",
                   return_value=(str(manifest_path), "")), \
             patch.object(self.widget, "confirm_plan", return_value=True):
            self.widget.import_publication_plan()
            self.widget._import_thread.wait(3000)
            self.app.processEvents()
        file.write_bytes(b"change")
        with patch.object(self.widget, "confirm_plan", return_value=True), \
             patch("telegram_media_sender.weekly_widget.themed_message"):
            self.widget.refresh()
            self.widget._import_thread.wait(3000)
            self.app.processEvents()
        self.assertIsNotNone(self.widget.imported_plan)
        self.assertEqual(self.widget.status.text(), self.widget.t("Cannot import publication plan"))


if __name__ == "__main__":
    unittest.main()
