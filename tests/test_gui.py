import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt, QPoint, QPointF, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QFrame, QStyle, QStyleOptionSlider, QHeaderView, QPushButton, QLineEdit, QListWidget

from telegram_media_sender.gui import (
    MediaSenderWindow, TelegramWorker, UploadCancelled, RoundedTableOverlay,
    CenteredSelectionPanel, CenteredTextButton, localized_exception,
)
from telegram_media_sender.storage import SenderStorage
from telegram_media_sender.i18n import tr


class MediaSenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.data_folder = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.data_folder.cleanup()

    def make_window(self, language="ru"):
        return MediaSenderWindow(language=language, persist_state=False,
                                 storage=SenderStorage(root=Path(self.data_folder.name)))

    def test_cancel_button_requests_safe_worker_cancel(self):
        worker = TelegramWorker()
        worker.request_cancel()
        with self.assertRaises(UploadCancelled):
            worker.check_cancel()

    def test_external_error_messages_are_localized(self):
        invalid_code = type("PhoneCodeInvalidError", (Exception,), {})
        for language in ("de", "ru", "en"):
            self.assertEqual(localized_exception(invalid_code("Invalid code"), language),
                             tr("The Telegram code is invalid or expired. Try signing in again.", language))
            self.assertEqual(localized_exception(PermissionError("Permission denied"), language),
                             tr("Could not access local data. Check folder permissions.", language))
            translated = tr("Telegram code was not received.", language)
            self.assertEqual(localized_exception(RuntimeError(translated), language), translated)

    def test_avatar_icons_are_round_and_compact_in_selectors(self):
        window = self.make_window()
        self.assertEqual(window.chat_combo.iconSize(), QSize(28, 28))
        self.assertEqual(window.profile_combo.iconSize(), QSize(28, 28))
        for icon in (window.chat_icon("Пример группы", None), window.profile_icon()):
            pixmap = icon.pixmap(48, 48)
            self.assertFalse(pixmap.isNull())
            image = pixmap.toImage()
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
            self.assertGreater(image.pixelColor(24, 24).alpha(), 0)
        window.close()

    def test_main_button_labels_fit_in_all_three_languages(self):
        for language in ("de", "ru", "en"):
            window = self.make_window(language)
            window.show()
            self.app.processEvents()
            for button in window.findChildren(QPushButton):
                if button.isVisible() and button.text():
                    self.assertLessEqual(button.sizeHint().width(), button.width(),
                                         f"{language}: {button.text()}")
            send_label = window.send_button.findChild(QLabel, "sendButtonLabel")
            self.assertLessEqual(send_label.sizeHint().width(), send_label.width(), language)
            self.assertLessEqual(send_label.sizeHint().height(), send_label.height(), language)
            window.close()

    def test_synthetic_old_default_is_absent_when_switching_languages(self):
        storage = SenderStorage(root=Path(self.data_folder.name))
        first = self.make_window("ru")
        synthetic = {"id": first.profile_store.LEGACY_DEFAULT_ID,
                     "name": "Существующий локальный профиль", "phone": "+49123",
                     "api_id": "123", "api_hash": "secret"}
        first.profile_store._write_profiles([synthetic])
        session = first.profile_store.session_path(synthetic, storage.root)
        session.write_bytes(b"saved session")
        first.close()
        for language in ("de", "ru", "en"):
            window = self.make_window(language)
            self.assertEqual(window.profile_combo.count(), 0)
            self.assertEqual(window.profile_store.load(), [])
            self.assertFalse(window.refresh_chats_button.isEnabled())
            self.assertEqual(session.read_bytes(), b"saved session")
            window.close()

    def test_wide_chat_photo_fits_inside_round_avatar_without_edge_crop(self):
        window = self.make_window()
        source = QPixmap(100, 50)
        source.fill(QColor("#ff0000"))
        painter = QPainter(source)
        painter.fillRect(50, 0, 50, 50, QColor("#00aa00"))
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        source.save(buffer, "PNG")

        result = window.chat_icon("Тестовая группа", bytes(buffer.data())).pixmap(48, 48).toImage()

        self.assertEqual(result.pixelColor(10, 24), QColor("#ff0000"))
        self.assertEqual(result.pixelColor(38, 24), QColor("#00aa00"))
        self.assertNotIn(result.pixelColor(24, 6), (QColor("#ff0000"), QColor("#00aa00")))
        self.assertEqual(result.pixelColor(0, 0).alpha(), 0)
        window.close()

    def test_cancel_control_enables_during_work_and_signals_worker(self):
        window = self.make_window()
        worker = SimpleNamespace(cancelled=False, request_cancel=lambda: setattr(worker, "cancelled", True))
        window.worker = worker
        window.set_busy(True, "Тест")
        self.assertTrue(window.cancel_button.isEnabled())
        window.cancel_button.click()
        self.assertTrue(worker.cancelled)
        self.assertFalse(window.cancel_button.isEnabled())
        window.worker = None
        window.set_busy(False, "Готово")
        window.close()

    def test_table_scrollbar_stays_active_during_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in range(1, 11):
                title = f"{number:04} Комплект {number}"
                (root / f"{title}.ru.mp4").write_bytes(b"video")
                (root / f"{title}.ru.srt").write_text("русский")
                (root / f"{title}.srt").write_text("Deutsch")

            window = self.make_window()
            window.folder = root
            window.scan()
            window.show()
            self.app.processEvents()
            bar = window.vertical_scrollbar
            self.assertGreater(bar.maximum(), 0)
            self.assertEqual(bar.height(), window.table_frame.height() - 2)
            self.assertEqual(bar.minimum(), window.table.verticalScrollBar().minimum())

            window.set_busy(True, "Загрузка")
            self.app.processEvents()
            self.assertTrue(window.table.isEnabled())
            self.assertTrue(bar.isEnabled())
            self.assertFalse(window.row_checks[0].isEnabled())
            panel = window.row_checks[0].parentWidget()
            self.assertIsInstance(panel, CenteredSelectionPanel)
            self.assertLessEqual(abs(2 * window.row_checks[0].x() +
                                     window.row_checks[0].width() - panel.width()), 1)
            target = min(bar.maximum(), 50)
            bar.setValue(target)
            self.app.processEvents()
            self.assertEqual(bar.value(), target)
            bar.setValue(0)
            slider = QStyleOptionSlider()
            bar.initStyleOption(slider)
            handle = bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, slider,
                                                QStyle.SubControl.SC_ScrollBarSlider, bar)
            start = handle.center()
            end = QPoint(start.x(), bar.height() - handle.height() // 2 - 1)
            QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(bar, end, delay=20)
            QTest.mouseRelease(bar, Qt.MouseButton.LeftButton,
                               pos=end)
            self.app.processEvents()
            self.assertGreater(bar.value(), 0, "Dragging the scrollbar must work during upload.")
            bar.setValue(0)
            row_check = window.row_checks[0]
            local = QPointF(row_check.rect().center())
            event = QWheelEvent(local, QPointF(row_check.mapToGlobal(local.toPoint())),
                QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.ScrollUpdate, False)
            QApplication.sendEvent(row_check, event)
            self.app.processEvents()
            self.assertGreater(bar.value(), 0, "Wheel scrolling over disabled row checkboxes must reach the table during upload.")
            bar.setValue(0)
            slider = QStyleOptionSlider()
            bar.initStyleOption(slider)
            handle = bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, slider,
                                                QStyle.SubControl.SC_ScrollBarSlider, bar)
            start = handle.center()
            end = QPoint(start.x(), bar.height() - handle.height() // 2 - 1)
            QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(bar, end, delay=20)
            QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=end)
            self.app.processEvents()
            self.assertGreater(bar.value(), 0, "The visible full-height scrollbar handle must reach the lower endpoint.")
            self.assertEqual(window.table.verticalScrollBar().value(), bar.value())
            window.close()

    def test_selected_design_has_centered_text_icons_and_status_badges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            title = "0002 Щитовидная железа"
            (root / f"{title}.ru.mp4").write_bytes(b"video")
            (root / f"{title}.ru.srt").write_text("русский")
            (root / f"{title}.srt").write_text("Deutsch")
            second_title = "0003 Здоровье и растения"
            (root / f"{second_title}.ru.mp4").write_bytes(b"video")
            (root / f"{second_title}.ru.srt").write_text("русский")
            (root / f"{second_title}.srt").write_text("Deutsch")

            window = self.make_window()
            window.folder = root
            window.scan()
            window.resize(1280, 864)
            window.show()
            self.app.processEvents()

            self.assertEqual(window.table.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.assertEqual(window.table.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.assertEqual(window.minimumSize(), QSize(1280, 864))
            self.assertEqual(window.maximumSize(), QSize(1280, 864))
            self.assertEqual(window.bottom_scrollbar_gutter.height(), 12)
            self.assertIsInstance(window.table.horizontalHeader(), QHeaderView)
            self.assertIsInstance(window.table_overlay, RoundedTableOverlay)
            self.assertEqual(window.table_overlay.radius, 13.0)
            self.assertEqual(window.table.columnWidth(0), 84)
            self.assertEqual(window.table.columnWidth(1), 342)
            self.assertTrue(window.table.horizontalHeader().defaultAlignment() & Qt.AlignmentFlag.AlignLeft)
            self.assertEqual(window.table.horizontalHeader().sectionResizeMode(1),
                             window.table.horizontalHeader().ResizeMode.Interactive)
            self.assertTrue(window.table.item(0, 1).textAlignment() & Qt.AlignmentFlag.AlignVCenter)
            self.assertTrue(window.table.item(0, 2).textAlignment() & Qt.AlignmentFlag.AlignVCenter)
            self.assertEqual(window.table.cellWidget(0, 3).findChild(QLabel, "rowStatus").text(), "В очереди")
            status_cell = window.table.cellWidget(0, 3)
            self.assertIsNone(status_cell.findChild(QFrame, "statusPanel"))
            self.assertEqual(status_cell.findChild(QLabel, "sizeValue").text(), "26.0 Б")
            self.assertIn("border-radius: 9px",
                          status_cell.findChild(QLabel, "rowStatus").styleSheet())
            self.assertEqual(window.cancel_button.size().width(), 104)
            self.assertEqual(window.cancel_button.size().height(), 44)
            for row_check in window.row_checks:
                selection_panel = row_check.parentWidget()
                self.assertIsInstance(selection_panel, CenteredSelectionPanel)
                self.assertLessEqual(abs(2 * row_check.x() + row_check.width() -
                                         selection_panel.width()), 1)
                self.assertLessEqual(abs(2 * row_check.y() + row_check.height() -
                                         selection_panel.height()), 1)

            window.set_group_status(title, "sent")
            self.assertEqual(window.table.cellWidget(0, 3).findChild(QLabel, "rowStatus").text(), "Отправлено")
            self.assertIn("border-radius: 9px",
                          window.table.cellWidget(0, 3).findChild(QLabel, "rowStatus").styleSheet())
            window.stage_label.setText("Этап 2/3 · Проверка")
            window.overall_progress.setValue(37)
            window.update_task_progress({"row_status": (title, "duplicate")})
            self.assertEqual(window.stage_label.text(), "Этап 2/3 · Проверка")
            self.assertEqual(window.overall_progress.value(), 37)
            for kind in ("Видео", "Аудио"):
                icon = window.media_icon(kind).pixmap(QSize(52, 52))
                self.assertFalse(icon.isNull())
                self.assertGreaterEqual(icon.devicePixelRatio(), 1)
            icon_label = window.send_button.findChild(QLabel, "sendButtonIcon")
            text_label = window.send_button.findChild(QLabel, "sendButtonLabel")
            self.assertGreaterEqual(text_label.geometry().left() - icon_label.geometry().right() - 1, 10)
            window.close()

    def test_send_confirmation_and_completion_summary_are_russian_and_multiline(self):
        window = self.make_window()
        box, yes = window.send_confirmation_dialog(2, "Тестовый чат", "• Комплект")
        self.assertEqual({button.text() for button in box.buttons()}, {"Да", "Отменить"})
        self.assertIsInstance(yes, CenteredTextButton)
        self.assertLessEqual(abs(2 * yes.label_rect().center().x() - yes.width() + 1), 1)
        self.assertLessEqual(abs(2 * yes.label_rect().center().y() - yes.height() + 1), 1)
        cancel = box.defaultButton()
        self.assertIsInstance(cancel, CenteredTextButton)
        self.assertEqual(cancel.height(), yes.height())
        box.adjustSize()
        box.show()
        QApplication.processEvents()
        self.assertEqual(cancel.geometry().top(), yes.geometry().top())
        self.assertEqual(cancel.geometry().height(), yes.geometry().height())
        self.assertEqual(box.defaultButton().text(), "Отменить")
        self.assertEqual(TelegramWorker.completion_summary(2, 0, "ru"),
            "Отправлено комплектов: 2\nПропущено повторов: 0\n"
            "Медиа отправлено отдельно от группового альбома субтитров.")
        box.close()
        window.close()

    def test_profile_and_sign_in_dialog_buttons_follow_selected_language(self):
        for language in ("ru", "de", "en"):
            window = self.make_window(language)
            observed = []

            def inspect_add():
                dialog = QApplication.activeModalWidget()
                observed.append({button.text() for button in dialog.findChildren(QPushButton)})
                fields = dialog.findChildren(QLineEdit)
                self.assertEqual(len(fields), 4)
                self.assertEqual(fields[-1].echoMode(), QLineEdit.EchoMode.Password)
                dialog.reject()

            QTimer.singleShot(0, inspect_add)
            self.assertIsNone(window.add_profile())
            self.assertIn(tr("Save", language), observed[0])
            self.assertIn(tr("Cancel", language), observed[0])

            def inspect_code():
                dialog = QApplication.activeModalWidget()
                observed.append({button.text() for button in dialog.findChildren(QPushButton)})
                self.assertEqual(dialog.findChild(QLineEdit).echoMode(), QLineEdit.EchoMode.Password)
                dialog.reject()

            context = (SimpleNamespace(set=lambda: None), {})
            QTimer.singleShot(0, inspect_code)
            window.request_worker_input(tr("Telegram two-step verification password", language), True, context)
            self.assertEqual(observed[1], {tr("OK", language), tr("Cancel", language)})
            self.assertEqual(context[1]["value"], "")
            window.close()

    def test_dialog_button_labels_fit_in_all_three_languages(self):
        for language in ("de", "ru", "en"):
            window = self.make_window(language)
            profile = window.profile_store.add("Temporary", f"+4900{language}", "99", "hash")
            window.reload_profiles()
            overflows = []

            def inspect_and_close():
                dialog = QApplication.activeModalWidget()
                self.app.processEvents()
                for button in dialog.findChildren(QPushButton):
                    if button.isVisible() and button.text() and button.sizeHint().width() > button.width():
                        overflows.append((language, dialog.windowTitle(), button.text(),
                                          button.sizeHint().width(), button.width()))
                dialog.reject()

            def check_modal(operation):
                QTimer.singleShot(0, inspect_and_close)
                operation()

            check_modal(window.manage_profiles)
            check_modal(window.add_profile)
            check_modal(lambda: window.confirm_profile_deletion(profile))
            check_modal(lambda: window.request_worker_input(
                tr("Telegram sign-in code", language), False,
                (SimpleNamespace(set=lambda: None), {})))
            check_modal(lambda: window.request_worker_input(
                tr("Telegram two-step verification password", language), True,
                (SimpleNamespace(set=lambda: None), {})))
            check_modal(lambda: window.show_message("information", tr("Language saved", language),
                                                     tr("Restart the app to apply the selected language.", language)))
            check_modal(lambda: window.review_duplicates(
                [{"name": "001 Temporary", "files": ["001 Temporary.mp4"]}],
                (SimpleNamespace(set=lambda: None), {})))
            confirmation, _yes = window.send_confirmation_dialog(1, "Temporary", "• 001 Temporary")
            confirmation.show()
            self.app.processEvents()
            for button in confirmation.buttons():
                if button.sizeHint().width() > button.width():
                    overflows.append((language, "Upload confirmation", button.text(),
                                      button.sizeHint().width(), button.width()))
            confirmation.close()
            self.assertEqual(overflows, [])
            window.close()

    def test_delete_dialog_order_spacing_and_cancel(self):
        window = self.make_window()
        profile = window.profile_store.add("Тестовый профиль", "+491234", "99", "hash")
        window.reload_profiles()

        def inspect_and_cancel():
            dialog = QApplication.activeModalWidget()
            buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
            self.assertEqual(set(buttons), {"Отменить", "Удалить"})
            self.assertLess(buttons["Отменить"].x(), buttons["Удалить"].x())
            self.assertLessEqual(buttons["Удалить"].x() - buttons["Отменить"].geometry().right(), 11)
            dialog.reject()

        QTimer.singleShot(0, inspect_and_cancel)
        self.assertFalse(window.confirm_profile_deletion(profile))
        self.assertEqual(len(window.profile_store.load()), 1)
        window.close()

    def test_manager_deletes_selected_and_last_profile_and_clears_chats(self):
        window = self.make_window()
        first = window.profile_store.add("Первый", "+491111", "99", "hash")
        second = window.profile_store.add("Второй", "+492222", "99", "hash")
        window.reload_profiles()
        window.profile_combo.setCurrentIndex(0)
        window.chat_combo.addItem("Temporary chat")
        window.chat_entities = [object()]

        def run_delete(expected_remaining):
            manager = QApplication.activeModalWidget()
            listing = manager.findChild(QListWidget, "profileList")
            self.assertIsNotNone(listing)
            listing.setCurrentRow(0)
            remove = next(button for button in manager.findChildren(QPushButton)
                          if button.text() == "Удалить…")

            def confirm():
                dialog = QApplication.activeModalWidget()
                delete = next(button for button in dialog.findChildren(QPushButton)
                              if button.text() == "Удалить")
                delete.click()

            QTimer.singleShot(0, confirm)
            remove.click()
            self.assertEqual(window.chat_combo.count(), 0)
            self.assertEqual(len(window.profiles), expected_remaining)
            manager.accept()

        QTimer.singleShot(0, lambda: run_delete(1))
        window.manage_profiles()
        self.assertEqual(window.current_profile()["id"], second["id"])
        QTimer.singleShot(0, lambda: run_delete(0))
        window.manage_profiles()
        self.assertEqual(window.profiles, [])
        self.assertFalse(window.send_button.isEnabled())
        self.assertFalse(window.refresh_chats_button.isEnabled())
        window.close()

    def test_profile_actions_block_while_worker_is_active(self):
        window = self.make_window()
        window.profile_store.add("Первый", "+491111", "99", "hash")
        window.reload_profiles()
        window.worker = SimpleNamespace()
        window.set_busy(True, "Работа")
        self.assertFalse(window.profile_combo.isEnabled())
        self.assertFalse(window.add_profile_button.isEnabled())
        self.assertIsNone(window.add_profile())
        self.assertIsNone(window.manage_profiles())
        window.worker = None
        window.close()

    def test_subtitle_only_bundle_is_displayed_without_media_icon_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "0013 Титры.ru.srt").write_text("русский")
            (root / "0013 Титры.de.srt").write_text("Deutsch")
            window = self.make_window()
            window.folder = root
            window.scan()
            self.assertEqual(len(window.groups), 1)
            self.assertEqual(window.groups[0].media, [])
            self.assertFalse(window.media_icon("Subtitle").isNull())
            self.assertEqual(window.table.rowCount(), 1)
            window.close()


if __name__ == "__main__":
    unittest.main()
