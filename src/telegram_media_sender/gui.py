"""Small macOS desktop UI for sending local media/subtitle triples to Telegram."""
from __future__ import annotations

import asyncio
import sqlite3
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, Signal, QPoint, QPointF, QRectF, QEvent, QObject, QSettings, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap, QPen, QLinearGradient, QWheelEvent, QPalette, QGuiApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QInputDialog,
    QProgressBar,
    QFrame,
    QLineEdit,
    QScrollBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QListView,
    QStyle,
    QStyleFactory,
    QStyleOptionButton,
    QHeaderView,
    QDialog,
    QListWidget,
    QListWidgetItem,
    QFormLayout,
)

from .i18n import CATALOG, LANGUAGE_LABELS, LANGUAGES, normalize_language, system_language, tr
from .media_groups import Group, GroupIssue, attachment_name_key, find_group_duplicates, scan_folder
from .permissions import can_publish
from .profiles import SenderProfileStore
from .storage import SenderStorage


class UploadCancelled(Exception):
    """Raised at a safe upload boundary after the user asks to stop."""


def localized_exception(error: Exception, language: str) -> str:
    """Keep expected local errors and replace library messages with app-language text."""
    message = str(error).strip()
    if message and any(message == tr(key, language) for key in CATALOG):
        return message
    name = type(error).__name__
    if name in {"ApiIdInvalidError", "ApiIdPublishedFloodError"}:
        key = "Telegram rejected the API ID or API Hash. Check the profile."
    elif name in {"PhoneCodeInvalidError", "PhoneCodeExpiredError", "PhoneCodeEmptyError"}:
        key = "The Telegram code is invalid or expired. Try signing in again."
    elif name == "PasswordHashInvalidError":
        key = "The two-step verification password is incorrect."
    elif name in {"ChatWriteForbiddenError", "UserBannedInChannelError", "ChatAdminRequiredError"}:
        key = "You cannot send messages to this chat."
    elif name == "FloodWaitError":
        key = "Telegram requests a pause before trying again."
    elif isinstance(error, (ConnectionError, TimeoutError)):
        key = "Could not connect to Telegram. Check the internet connection."
    elif isinstance(error, (OSError, sqlite3.Error)):
        key = "Could not access local data. Check folder permissions."
    else:
        key = "Telegram could not complete the request. Check your connection and account."
    return tr(key, language)


class ScrollWheelForwarder(QObject):
    """Forward wheel events from disabled row selectors into the table viewport."""

    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self.table = table

    def eventFilter(self, watched, event) -> bool:
        if event.type() != QEvent.Type.Wheel or not self.table.isEnabled():
            return False
        viewport = self.table.viewport()
        position = viewport.mapFromGlobal(event.globalPosition().toPoint())
        forwarded = QWheelEvent(
            QPointF(position), QPointF(viewport.mapToGlobal(position)),
            event.pixelDelta(), event.angleDelta(), event.buttons(), event.modifiers(),
            event.phase(), event.inverted(), event.source(),
        )
        QApplication.sendEvent(viewport, forwarded)
        if forwarded.isAccepted():
            event.accept()
            return True
        return False


class RoundedTableOverlay(QWidget):
    """Clip square child-widget corners and draw one continuous table outline."""

    def __init__(self, parent: QWidget, background: str = "#f3f6fc"):
        super().__init__(parent)
        self.background = QColor(background)
        self.border = QColor("#dce6f4")
        self.radius = 13.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        parent.installEventFilter(self)
        self.setGeometry(parent.rect())
        self.raise_()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.setGeometry(watched.rect())
            scrollbar = watched.findChild(RoundedScrollBar, "fullHeightVerticalScrollBar")
            if scrollbar is not None:
                scrollbar.setGeometry(watched.width() - scrollbar.width() - 1, 1,
                                      scrollbar.width(), max(0, watched.height() - 2))
            self.raise_()
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.raise_()

    def paintEvent(self, _event) -> None:
        bounds = QRectF(self.rect())
        inner = bounds.adjusted(1, 1, -1, -1)
        outer_path = QPainterPath()
        outer_path.addRect(bounds)
        inner_path = QPainterPath()
        inner_path.addRoundedRect(inner, self.radius - 1, self.radius - 1)
        outside_path = outer_path.subtracted(inner_path)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillPath(outside_path, self.background)
        border_path = QPainterPath()
        border_path.addRoundedRect(bounds.adjusted(0.5, 0.5, -0.5, -0.5),
                                   self.radius, self.radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self.border, 1.0))
        painter.drawPath(border_path)
        table = self.parentWidget().findChild(QTableWidget)
        if table is not None:
            header = table.horizontalHeader()
            separator_y = header.mapTo(self.parentWidget(), QPoint(0, header.height())).y()
            scrollbar_left = table.verticalScrollBar().mapTo(
                self.parentWidget(), QPoint(0, 0)
            ).x()
            painter.setPen(QPen(self.border, 1.0))
            painter.drawLine(QPointF(1, separator_y - 0.5),
                             QPointF(scrollbar_left, separator_y - 0.5))
        painter.end()


class CenteredSelectionPanel(QFrame):
    """Place its checkbox at the exact geometric center across native styles."""

    def __init__(self, checkbox: QCheckBox, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("selectionPanel")
        self.checkbox = checkbox
        checkbox.setParent(self)
        self.center_checkbox()

    def center_checkbox(self) -> None:
        x = round((self.width() - self.checkbox.width()) / 2)
        y = round((self.height() - self.checkbox.height()) / 2)
        self.checkbox.setGeometry(x, y, self.checkbox.width(), self.checkbox.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.center_checkbox()


class CenteredTextButton(QPushButton):
    """Keep the native button bevel while centering its label without style offsets."""

    def label_rect(self):
        return self.rect().adjusted(1, 1, -1, -1)

    def paintEvent(self, _event) -> None:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        label = self.text()
        option.text = ""
        option.icon = QIcon()
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)
        role = QPalette.ColorRole.ButtonText
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        painter.setPen(self.palette().color(group, role))
        painter.setFont(self.font())
        painter.drawText(self.label_rect(),
                         Qt.AlignmentFlag.AlignCenter, label)
        painter.end()


class RoundedScrollBar(QScrollBar):
    """Paint a slim scrollbar with inset, rounded ends on both axes."""

    def __init__(self, orientation: Qt.Orientation, parent=None):
        super().__init__(orientation, parent)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#e6edf7"))
        vertical = self.orientation() == Qt.Orientation.Vertical
        if vertical:
            track = QRectF(4, 8, max(0, self.width() - 8), max(0, self.height() - 16))
        else:
            track = QRectF(8, 4, max(0, self.width() - 16), max(0, self.height() - 8))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e6edf7"))
        painter.drawRoundedRect(track, 5, 5)
        if self.maximum() <= self.minimum() or track.isEmpty():
            return
        track_length = track.height() if vertical else track.width()
        page = max(1, self.pageStep())
        handle_length = min(track_length, max(34.0, track_length * page /
                                             (self.maximum() - self.minimum() + page)))
        travel = max(0.0, track_length - handle_length)
        value_range = max(1, self.maximum() - self.minimum())
        offset = travel * (self.value() - self.minimum()) / value_range
        if vertical:
            handle = QRectF(track.left() + 1, track.top() + offset,
                            max(0, track.width() - 2), handle_length)
        else:
            handle = QRectF(track.left() + offset, track.top() + 1,
                            handle_length, max(0, track.height() - 2))
        painter.setBrush(QColor("#086ee4" if self.underMouse() else "#1680ed"))
        painter.drawRoundedRect(handle, 4, 4)


class TelegramWorker(QThread):
    chats_ready = Signal(object)
    progress = Signal(str)
    completed = Signal(str)
    cancelled = Signal(str)
    failed = Signal(str)
    input_requested = Signal(str, bool, object)
    duplicate_check = Signal(str)
    duplicate_review = Signal(object, object)
    task_progress = Signal(object)

    @staticmethod
    def completion_summary(sent: int, skipped: int, language: str = "en") -> str:
        return tr("Sent groups: {sent}\nSkipped duplicates: {skipped}\n{note}", language,
                  sent=sent, skipped=skipped,
                  note=tr("Uploading media groups separately from the subtitle album.", language))

    def __init__(self, *, groups: list[Group] | None = None, target=None, profile=None, profile_store=None,
                 language: str = "en"):
        super().__init__()
        self.groups = groups
        self.target = target
        self.profile = profile
        self.profile_store = profile_store
        self.language = normalize_language(language)
        self._cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def check_cancel(self) -> None:
        if self._cancel_event.is_set():
            raise UploadCancelled(tr("Upload cancelled by the user.", self.language))

    def ask_input(self, prompt: str, secret: bool = False) -> str:
        event = threading.Event()
        answer = {"value": ""}
        self.input_requested.emit(prompt, secret, (event, answer))
        if not event.wait(300):
            raise RuntimeError(tr("Telegram code was not received.", self.language))
        if not answer["value"]:
            raise RuntimeError(tr("Telegram sign-in cancelled.", self.language))
        return answer["value"]

    def ask_duplicate_review(self, duplicates: list[dict]) -> str:
        event = threading.Event()
        answer = {"choice": "cancel"}
        self.duplicate_review.emit(duplicates, (event, answer))
        if not event.wait(300):
            raise RuntimeError(tr("Duplicate review was not received.", self.language))
        return answer["choice"]

    def run(self) -> None:
        try:
            asyncio.run(self._work())
        except UploadCancelled as error:
            self.cancelled.emit(str(error))
        except Exception as error:
            self.failed.emit(localized_exception(error, self.language))

    async def _work(self) -> None:
        self.task_progress.emit({"phase": tr("Stage 1/3 · Connecting to Telegram", self.language), "overall": 0})
        storage = SenderStorage(language=self.language)
        profile = self.profile
        if profile is None:
            raise RuntimeError(tr("Add a Telegram profile before loading chats.", self.language))
        session = self.profile_store.session_path(profile, storage.root)
        if not profile.get("api_id") or not profile.get("api_hash"):
            raise RuntimeError(tr("Fill in the API ID and API Hash in the profile.", self.language))

        from telethon import TelegramClient

        client = TelegramClient(str(session), int(profile["api_id"]), profile["api_hash"])
        try:
            self.check_cancel()
            await client.connect()
            self.check_cancel()
            if not await client.is_user_authorized():
                if not profile.get("phone"):
                    raise RuntimeError(tr("The profile has no phone number.", self.language))
                sent_code = await client.send_code_request(profile["phone"])
                code = await asyncio.to_thread(self.ask_input, tr("Telegram sign-in code", self.language), False)
                try:
                    await client.sign_in(profile["phone"], code, phone_code_hash=sent_code.phone_code_hash)
                except Exception as error:
                    from telethon.errors import SessionPasswordNeededError
                    if not isinstance(error, SessionPasswordNeededError):
                        raise
                    password = await asyncio.to_thread(self.ask_input, tr("Telegram two-step verification password", self.language), True)
                    await client.sign_in(password=password)
            if self.groups is None:
                dialogs = []
                async for dialog in client.iter_dialogs():
                    self.check_cancel()
                    if can_publish(dialog.entity):
                        photo = None
                        try:
                            photo = await client.download_profile_photo(dialog.entity, file=bytes, download_big=False)
                        except Exception:
                            pass
                        dialogs.append((dialog.name, dialog.entity, photo))
                self.chats_ready.emit(dialogs)
                return

            # Compare attachment filename and byte size with this exact recipient's
            # history. If Telegram accepted a group just before the connection broke,
            # a retry in a later run must not publish those files again.
            self.task_progress.emit({"phase": tr("Stage 1/3 · Checking chat for duplicates", self.language), "overall": 0})
            existing = set()
            async for message in client.iter_messages(self.target, limit=None):
                self.check_cancel()
                file = getattr(message, "file", None)
                name, size = getattr(file, "name", None), getattr(file, "size", None)
                if name and type(size) is int:
                    existing.add((attachment_name_key(name), size))
            self.check_cancel()
            duplicates = find_group_duplicates(self.groups, existing)
            choice = "all"
            if duplicates:
                choice = await asyncio.to_thread(self.ask_duplicate_review, duplicates)
                if choice == "cancel":
                    self.cancelled.emit(tr("Upload stopped. Review the matching groups.", self.language))
                    return
            for duplicate in duplicates:
                self.task_progress.emit({"row_status": (duplicate["name"], "duplicate")})
            duplicate_indexes = {item["index"] for item in duplicates}
            to_send = ([group for index, group in enumerate(self.groups) if index not in duplicate_indexes]
                       if choice == "skip" else self.groups)
            if not to_send:
                self.cancelled.emit(tr("All selected groups were skipped as duplicates.", self.language))
                return

            total_bytes = sum(path.stat().st_size for group in to_send for path in group.files)
            completed_bytes = 0
            skipped_count = len(self.groups) - len(to_send)
            for index, group in enumerate(to_send, 1):
                sizes = [path.stat().st_size for path in group.files]
                group_bytes = sum(sizes)
                group_done = 0
                label = tr("Group {index}/{total} · {name}", self.language,
                           index=index, total=len(to_send), name=group.name)
                self.task_progress.emit({"row_status": (group.name, "sending")})

                async def send_segment(paths: list[Path], title: str, *, force_document=False,
                                       supports_streaming=False):
                    nonlocal group_done
                    self.check_cancel()
                    segment_sizes = [path.stat().st_size for path in paths]
                    file_index, last_value, segment_done = 0, 0.0, 0
                    self.task_progress.emit({"phase": tr("Stage 2/3 · {title} · group {index}/{total}", self.language,
                        title=title, index=index, total=len(to_send)),
                        "overall": int(5 + 90 * (completed_bytes + group_done) / max(total_bytes, 1)),
                        "group": int(100 * group_done / max(group_bytes, 1)), "group_text": label,
                        "file": tr("Preparing · {name}", self.language, name=paths[0].name), "file_progress": 0})

                    def upload_progress(current, total):
                        nonlocal file_index, last_value, segment_done
                        self.check_cancel()
                        if len(paths) > 1 and total == len(paths) and 0 <= current <= total:
                            position = min(float(current), float(len(paths)))
                            file_index = min(int(position), len(paths) - 1)
                            fraction = position - file_index
                            current_bytes = int(segment_sizes[file_index] * fraction)
                        else:
                            if current < last_value:
                                file_index = min(file_index + 1, len(paths) - 1)
                            last_value = current
                            fraction = min(max(float(current) / max(float(total), 1), 0), 1)
                            current_bytes = int(segment_sizes[file_index] * fraction)
                        segment_done = sum(segment_sizes[:file_index]) + current_bytes
                        in_group = group_done + segment_done
                        self.task_progress.emit({"phase": tr("Stage 2/3 · {title} · group {index}/{total}", self.language,
                            title=title, index=index, total=len(to_send)),
                            "overall": int(5 + 90 * (completed_bytes + in_group) / max(total_bytes, 1)),
                            "group": int(100 * in_group / max(group_bytes, 1)), "group_text": label,
                            "file": f"{title}: {paths[file_index].name}", "file_progress": int(100 * fraction)})

                    await client.send_file(self.target, [str(path) for path in paths] if len(paths) > 1 else str(paths[0]),
                        force_document=force_document, supports_streaming=supports_streaming,
                        nosound_video=True, progress_callback=upload_progress)
                    self.check_cancel()
                    group_done += sum(segment_sizes)

                try:
                    for media in group.media:
                        suffix = media.suffix.casefold()
                        is_video = suffix in {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi"}
                        await send_segment([media], tr("Video" if is_video else "Audio", self.language),
                            supports_streaming=is_video and suffix in {".mp4", ".m4v"})
                    # Send every matched SRT, in Telegram-sized document batches.
                    subtitles = group.russian + group.german
                    for start in range(0, len(subtitles), 10):
                        await send_segment(subtitles[start:start + 10],
                                           tr("subtitles", self.language), force_document=True)
                except Exception:
                    self.task_progress.emit({"row_status": (group.name, "error")})
                    raise
                self.task_progress.emit({"row_status": (group.name, "sent")})
                completed_bytes += group_bytes
                self.task_progress.emit({"phase": tr("Stage 2/3 · Sent groups {index}/{total}", self.language,
                    index=index, total=len(to_send)),
                    "overall": int(5 + 90 * completed_bytes / max(total_bytes, 1)),
                    "group": 100, "group_text": tr("Group {index}/{total} · {name}", self.language,
                        index=index, total=len(to_send), name=group.name),
                    "file": tr("Group transferred to Telegram", self.language), "file_progress": 100})
            self.task_progress.emit({"phase": tr("Stage 3/3 · Finishing upload", self.language), "overall": 100,
                                     "group": 100, "file": tr("Done", self.language), "file_progress": 100})
            self.completed.emit(self.completion_summary(len(to_send), skipped_count, self.language))
        finally:
            await client.disconnect()


class SelectionCheckBox(QCheckBox):
    """A compact rounded selection control with a hand-drawn check mark."""

    def sizeHint(self):
        return QSize(38, 36)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = 22
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        if self.isChecked():
            painter.setPen(QPen(QColor("#1680ed"), 1.2))
            painter.setBrush(QColor("#1680ed"))
        else:
            painter.setPen(QPen(QColor("#b7c8de"), 1.6))
            painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 6, 6)
        if self.isChecked():
            mark = QPainterPath()
            mark.moveTo(rect.left() + 5.2, rect.center().y() + 0.1)
            mark.lineTo(rect.left() + 9.1, rect.center().y() + 4)
            mark.lineTo(rect.right() - 4.6, rect.center().y() - 4.3)
            painter.setPen(QPen(QColor("#ffffff"), 2.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(mark)
        painter.end()


class PopupComboBox(QComboBox):
    """A light popup whose complete window is painted by the application."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyle(QStyleFactory.create("Fusion"))
        self._popup: LightComboPopup | None = None
        self.setPalette(light_palette())
        self.setStyleSheet("""
            QComboBox { background: #ffffff; color: #213653; border: 1px solid #d5dfed;
                        border-radius: 10px; padding: 7px 40px 7px 10px; }
            QComboBox:hover, QComboBox:focus { border-color: #8fb8ed; }
            QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;
                                   width: 32px; border: 0; }
            QComboBox::down-arrow { image: none; width: 0; height: 0; }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(48)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() - 19, self.height() / 2)
        chevron = QPainterPath()
        chevron.moveTo(center.x() - 4.5, center.y() - 2)
        chevron.lineTo(center.x(), center.y() + 2.5)
        chevron.lineTo(center.x() + 4.5, center.y() - 2)
        painter.setPen(QPen(QColor("#536987"), 1.9, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(chevron)
        painter.end()

    def showPopup(self) -> None:
        if self.count() == 0:
            return
        self._popup = LightComboPopup(self)
        self._popup.show_for(self)

    def hidePopup(self) -> None:
        if self._popup is not None:
            self._popup.close()
            self._popup = None


def light_palette() -> QPalette:
    palette = QPalette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        palette.setColor(group, QPalette.ColorRole.Window, QColor("#f3f6fc"))
        palette.setColor(group, QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(group, QPalette.ColorRole.AlternateBase, QColor("#f8faff"))
        palette.setColor(group, QPalette.ColorRole.Button, QColor("#ffffff"))
        palette.setColor(group, QPalette.ColorRole.WindowText, QColor("#1c2d49"))
        palette.setColor(group, QPalette.ColorRole.Text, QColor("#1c2d49"))
        palette.setColor(group, QPalette.ColorRole.ButtonText, QColor("#1c2d49"))
        palette.setColor(group, QPalette.ColorRole.Highlight, QColor("#e6f1ff"))
        palette.setColor(group, QPalette.ColorRole.HighlightedText, QColor("#17477f"))
    return palette


class LightComboPopup(QWidget):
    """A rounded Qt popup without the native dark menu surround."""

    def __init__(self, combo: PopupComboBox):
        super().__init__(combo, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.combo = combo
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setPalette(light_palette())
        self.list = QListWidget(self)
        self.list.setPalette(light_palette())
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setStyleSheet("""
            QListWidget { background: transparent; color: #263a57; border: 0; outline: 0; }
            QListWidget::item { border-radius: 8px; padding: 6px 10px; }
            QListWidget::item:hover { background: #f2f7ff; }
            QListWidget::item:selected { background: #e6f1ff; color: #17477f; }
        """)
        self.list.itemClicked.connect(self._choose)
        self.list.itemActivated.connect(self._choose)
        inner = QVBoxLayout(self)
        inner.setContentsMargins(6, 6, 6, 6)
        inner.addWidget(self.list)

    def show_for(self, combo: PopupComboBox) -> None:
        for index in range(combo.count()):
            item = QListWidgetItem(combo.itemIcon(index), combo.itemText(index))
            item.setSizeHint(QSize(0, 46))
            self.list.addItem(item)
        self.list.setCurrentRow(combo.currentIndex())
        width = max(combo.width(), 180)
        height = min(combo.count(), 8) * 46 + 12
        self.resize(width, height)
        screen = QGuiApplication.screenAt(combo.mapToGlobal(QPoint(0, 0))) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        below = combo.mapToGlobal(QPoint(0, combo.height() + 4))
        y = below.y() if below.y() + height <= area.bottom() else combo.mapToGlobal(QPoint(0, -height - 4)).y()
        preferred_x = below.x() - max(0, width - combo.width())
        x = min(max(preferred_x, area.left()), area.right() - width + 1)
        self.move(x, y)
        self.show()
        self.list.setFocus()

    def _choose(self, item: QListWidgetItem) -> None:
        index = self.list.row(item)
        self.combo.setCurrentIndex(index)
        self.combo.hidePopup()

    def closeEvent(self, event) -> None:
        self.combo._popup = None
        super().closeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#d5dfed"), 1.0))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 12, 12)
        painter.end()


def style_light_dialog(dialog: QDialog) -> None:
    dialog.setPalette(light_palette())
    dialog.setStyleSheet("""
        QDialog, QMessageBox { background: #f3f6fc; color: #1c2d49; font-size: 13px; }
        QLabel { background: transparent; color: #1c2d49; }
        QLineEdit { background: #ffffff; color: #1c2d49; selection-background-color: #e6f1ff;
                    border: 1px solid #d5dfed; border-radius: 9px; padding: 8px 11px;
                    min-height: 24px; }
        QLineEdit:focus { border-color: #8fb8ed; }
        QPushButton { background: #ffffff; color: #1c2d49; border: 1px solid #d5dfed;
                      border-radius: 9px; padding: 8px 14px; min-height: 26px; }
        QPushButton:hover { background: #f0f6ff; border-color: #9abbea; }
        QListWidget { background: #ffffff; color: #1c2d49; border: 1px solid #d5dfed;
                      border-radius: 10px; outline: 0; padding: 5px; }
        QListWidget::item { padding: 7px 10px; border-radius: 7px; }
        QListWidget::item:selected { background: #e6f1ff; color: #17477f; }
    """)


def dialog_button(label: str, dialog: QDialog, *, default: bool = False) -> QPushButton:
    button = QPushButton(label, dialog)
    button.setFixedHeight(44)
    button.setDefault(default)
    return button


class MediaSenderWindow(QMainWindow):
    def __init__(self, language: str | None = None, *, persist_state: bool = True,
                 storage: SenderStorage | None = None):
        super().__init__()
        self.persist_state = persist_state
        self.settings = QSettings("TelegramMediaSender", "TelegramMediaSender")
        self.language = normalize_language(language or self.settings.value("language", system_language()))
        self.storage = storage or SenderStorage(language=self.language)
        self.setWindowTitle(self.t("Telegram Media Sender"))
        self.setFixedSize(1280, 864)
        self.setPalette(light_palette())
        self.folder: Path | None = None
        self.groups: list[Group] = []
        self.row_checks: list[QCheckBox] = []
        self.worker: TelegramWorker | None = None
        self.chat_entities = []
        self.profile_store = SenderProfileStore(self.storage.root, self.language)
        self.migration_error = None
        try:
            self.profile_store.migrate_from_legacy(self.storage.legacy_archive_root)
            self.profile_store.remove_auto_imported_legacy_profile()
        except (OSError, ValueError, sqlite3.Error) as error:
            self.migration_error = localized_exception(error, self.language)
        self.profiles = []

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setSpacing(16)
        logo = QLabel()
        logo.setObjectName("appLogo")
        logo.setFixedSize(68, 68)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(self.sender_icon().pixmap(68, 68))
        header.addWidget(logo)
        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        heading = QLabel(self.t("Telegram Media Sender"))
        heading.setObjectName("appTitle")
        header_text.addWidget(heading)
        intro = QLabel(
            self.t("Select a recipient, a folder, and send media groups")
        )
        intro.setWordWrap(True)
        intro.setObjectName("appIntro")
        header_text.addWidget(intro)
        header.addLayout(header_text, 1)
        header.addWidget(QLabel(self.t("Language")))
        self.language_combo = PopupComboBox()
        self.language_combo.setFixedSize(140, 44)
        self.language_combo.addItems([LANGUAGE_LABELS[code] for code in LANGUAGES])
        self.language_combo.setCurrentIndex(LANGUAGES.index(self.language))
        self.language_combo.currentIndexChanged.connect(self.language_changed)
        header.addWidget(self.language_combo)
        layout.addLayout(header)
        self.setWindowIcon(self.sender_icon())

        target_profile_card = QFrame()
        target_profile_card.setObjectName("surfaceCard")
        target_profile_layout = QHBoxLayout(target_profile_card)
        target_profile_layout.setContentsMargins(14, 10, 14, 10)
        target_profile_layout.setSpacing(16)

        target_column = QVBoxLayout()
        target_column.setSpacing(5)
        target_column.addWidget(QLabel(self.t("Where to send")))
        target_controls = QHBoxLayout()
        target_controls.setSpacing(8)
        self.chat_combo = PopupComboBox()
        self.chat_combo.setMinimumWidth(260)
        self.chat_combo.setIconSize(QSize(28, 28))
        target_controls.addWidget(self.chat_combo, 1)
        self.refresh_chats_button = QPushButton(self.t("Refresh"))
        self.refresh_chats_button.setObjectName("subtleButton")
        self.refresh_chats_button.clicked.connect(self.load_chats)
        target_controls.addWidget(self.refresh_chats_button)
        target_column.addLayout(target_controls)
        target_profile_layout.addLayout(target_column, 1)

        profile_column = QVBoxLayout()
        profile_column.setSpacing(5)
        profile_column.addWidget(QLabel(self.t("Telegram account")))
        profile_controls = QHBoxLayout()
        profile_controls.setSpacing(8)
        self.profile_combo = PopupComboBox()
        self.profile_combo.setMinimumWidth(260)
        self.profile_combo.currentIndexChanged.connect(self.profile_changed)
        self.profile_combo.setIconSize(QSize(28, 28))
        profile_controls.addWidget(self.profile_combo, 1)
        self.add_profile_button = QPushButton(self.t("Profiles…"))
        self.add_profile_button.setObjectName("subtleButton")
        self.add_profile_button.clicked.connect(self.manage_profiles)
        profile_controls.addWidget(self.add_profile_button)
        profile_column.addLayout(profile_controls)
        target_profile_layout.addLayout(profile_column, 1)
        layout.addWidget(target_profile_card)
        self.reload_profiles()

        folder_card = QFrame()
        folder_card.setObjectName("surfaceCard")
        folder_outer = QVBoxLayout(folder_card)
        folder_outer.setContentsMargins(14, 9, 14, 11)
        folder_outer.setSpacing(5)
        folder_title = QLabel(self.t("Media group folder"))
        folder_title.setObjectName("fieldTitle")
        folder_outer.addWidget(folder_title)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.folder_label = QLabel(self.t("No folder selected"))
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.folder_label.setWordWrap(True)
        self.choose_folder_button = QPushButton(self.t("Choose…"))
        self.choose_folder_button.setMinimumWidth(128)
        self.choose_folder_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(self.choose_folder_button)
        self.folder_label.setObjectName("folderPath")
        folder_outer.addLayout(folder_row)
        layout.addWidget(folder_card)

        list_card = QFrame()
        list_card.setObjectName("listCard")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        list_toolbar = QHBoxLayout()
        list_toolbar.setContentsMargins(14, 8, 14, 8)
        list_toolbar.setSpacing(12)
        self.selection_count = QLabel(self.t("No groups found"))
        self.selection_count.setObjectName("selectionBadge")
        self.select_all_button = QPushButton(self.t("Select all"))
        self.clear_button = QPushButton(self.t("Clear selection"))
        self.select_all_button.clicked.connect(lambda: self.set_all_checks(Qt.CheckState.Checked))
        self.clear_button.clicked.connect(lambda: self.set_all_checks(Qt.CheckState.Unchecked))
        list_toolbar.addStretch(1)
        list_toolbar.addWidget(self.selection_count)
        list_toolbar.addWidget(self.select_all_button)
        list_toolbar.addWidget(self.clear_button)
        list_layout.addLayout(list_toolbar)

        self.table_frame = QFrame()
        self.table_frame.setObjectName("tableFrame")
        table_frame_layout = QVBoxLayout(self.table_frame)
        table_frame_layout.setContentsMargins(1, 1, 1, 1)
        table_frame_layout.setSpacing(0)
        table_content = QWidget()
        table_content_layout = QHBoxLayout(table_content)
        table_content_layout.setContentsMargins(0, 0, 0, 0)
        table_content_layout.setSpacing(0)
        self.table = QTableWidget(0, 4)
        table_content_layout.addWidget(self.table, 1)
        scrollbar_inset = QWidget()
        scrollbar_inset.setFixedWidth(16)
        table_content_layout.addWidget(scrollbar_inset)
        table_frame_layout.addWidget(table_content, 1)
        self.bottom_scrollbar_gutter = QWidget()
        self.bottom_scrollbar_gutter.setObjectName("bottomScrollbarGutter")
        self.bottom_scrollbar_gutter.setFixedHeight(12)
        table_frame_layout.addWidget(self.bottom_scrollbar_gutter)
        self.scroll_wheel_forwarder = ScrollWheelForwarder(self.table)
        self.table.setHorizontalHeader(QHeaderView(Qt.Orientation.Horizontal, self.table))
        self.table.setHorizontalHeaderLabels([self.t(key) for key in ("Selection", "Group name", "Group files", "Size and status")])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table_vertical_scrollbar = self.table.verticalScrollBar()
        self.vertical_scrollbar = RoundedScrollBar(Qt.Orientation.Vertical, self.table_frame)
        self.vertical_scrollbar.setObjectName("fullHeightVerticalScrollBar")
        self.vertical_scrollbar.setFixedWidth(16)
        self.vertical_scrollbar.valueChanged.connect(self.table_vertical_scrollbar.setValue)
        self.table_vertical_scrollbar.valueChanged.connect(self.vertical_scrollbar.setValue)
        self.table_vertical_scrollbar.rangeChanged.connect(self.sync_vertical_scrollbar)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 84)
        self.table.setColumnWidth(1, 342)
        self.table.setColumnWidth(2, 526)
        self.table.setColumnWidth(3, 208)
        self._table_columns_initialized = False
        list_layout.addWidget(self.table_frame, 1)
        self.table_overlay = RoundedTableOverlay(self.table_frame)
        self.position_vertical_scrollbar()
        layout.addWidget(list_card, 1)

        self.status = QLabel(self.t("Choose a folder and load the chat list."))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        progress_card = QFrame()
        progress_card.setObjectName("progressCard")
        progress_layout = QHBoxLayout(progress_card)
        progress_layout.setContentsMargins(18, 14, 18, 14)
        progress_layout.setSpacing(18)
        progress_details = QVBoxLayout()
        progress_details.setSpacing(5)
        self.stage_label = QLabel(self.t("Send to Telegram"))
        self.stage_label.setObjectName("stageLabel")
        progress_details.addWidget(self.stage_label)
        self.file_progress_label = QLabel(self.t("File: —"))
        self.file_progress_label.setWordWrap(True)
        self.file_progress_label.setObjectName("progressDetail")
        progress_details.addWidget(self.file_progress_label)
        self.group_progress_label = QLabel(self.t("Group: —"))
        self.group_progress_label.setObjectName("progressDetail")
        progress_details.addWidget(self.group_progress_label)
        progress_layout.addLayout(progress_details, 1)

        progress_bars = QVBoxLayout()
        progress_bars.setSpacing(8)
        self.file_progress = self.make_progress("%p%")
        self.group_progress = self.make_progress("%p%")
        self.overall_progress = self.make_progress("%p%")
        progress_bars.addLayout(self.progress_row(self.t("Current file"), self.file_progress))
        progress_bars.addLayout(self.progress_row(self.t("Media group"), self.group_progress))
        progress_bars.addLayout(self.progress_row(self.t("All uploads"), self.overall_progress))
        self.overall_progress.setObjectName("overallProgress")
        progress_layout.addLayout(progress_bars, 2)

        send_column = QVBoxLayout()
        send_column.addStretch(1)
        self.send_button = QPushButton()
        self.send_button.setObjectName("sendButton")
        self.send_button.setMinimumSize(200, 76)
        self.send_button.setToolTip(self.t("Send selected media groups to Telegram"))
        self.send_button.setAccessibleName(self.t("Send selected groups"))
        send_button_layout = QHBoxLayout(self.send_button)
        send_button_layout.setContentsMargins(14, 8, 18, 8)
        send_button_layout.setSpacing(12)
        send_button_layout.addStretch(1)
        send_icon = QLabel()
        send_icon.setObjectName("sendButtonIcon")
        send_icon.setPixmap(self.telegram_plane_icon().pixmap(24, 24))
        send_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        send_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        send_button_layout.addWidget(send_icon)
        send_label = QLabel(self.t("Send selected\ngroups"))
        send_label.setObjectName("sendButtonLabel")
        send_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        send_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        send_button_layout.addWidget(send_label)
        send_button_layout.addStretch(1)
        self.send_button.setDefault(True)
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.send_selected)
        self.cancel_button = QPushButton(self.t("Cancel"))
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setFixedSize(104, 44)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setToolTip(self.t("Stop the current operation"))
        self.cancel_button.clicked.connect(self.cancel_operation)
        action_buttons = QHBoxLayout()
        action_buttons.setSpacing(14)
        action_buttons.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignVCenter)
        action_buttons.addWidget(self.send_button)
        send_column.addLayout(action_buttons)
        send_column.addStretch(1)
        progress_layout.addLayout(send_column)
        layout.addWidget(progress_card)

        self.setCentralWidget(page)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f3f6fc; color: #1c2d49; font-size: 13px; }
            QLabel { background: transparent; }
            QLabel#appTitle { font-size: 24px; font-weight: 750; color: #172b4d; }
            QLabel#appIntro { color: #65758f; font-size: 13px; }
            QLabel#secondaryNote { color: #536782; background: #e9f1fc; border: 1px solid #d8e5f7; border-radius: 11px; padding: 8px 12px; }
            QLabel#fieldTitle { color: #526783; font-size: 12px; font-weight: 600; }
            QLabel#folderPath { color: #526783; }
            QLabel#progressDetail { color: #647794; font-size: 11px; }
            QLabel#progressRowTitle { color: #526783; font-size: 12px; }
            QLabel#appLogo { background: transparent; }
            QLabel#stageLabel { color: #213958; font-size: 14px; font-weight: 700; padding-bottom: 3px; }
            QLabel#selectionBadge { color: #166dd0; background: #e8f2ff; border: 1px solid #d6e8ff; border-radius: 14px; padding: 7px 12px; font-weight: 650; }
            QFrame#surfaceCard, QFrame#progressCard { background: #ffffff; border: 1px solid #dce6f4; border-radius: 13px; }
            QPushButton { background: white; border: 1px solid #d5dfed; border-radius: 9px; padding: 8px 13px; }
            QPushButton:hover { background: #f0f6ff; border-color: #9abbea; }
            QPushButton:disabled { color: #9aa8ba; background: #edf1f7; }
            QPushButton#subtleButton { padding: 7px 12px; }
            QPushButton#sendButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #18a2ed, stop:1 #075ee1); color: white; border: 0; border-radius: 13px; padding: 12px 16px; }
            QLabel#sendButtonLabel { color: white; background: transparent; font-size: 14px; font-weight: 700; }
            QLabel#sendButtonIcon { background: transparent; }
            QPushButton#sendButton:hover { background: #096bd5; }
            QPushButton#sendButton:disabled { background: #9bbde2; color: #f4f8fc; }
            QPushButton#cancelButton { background: #fff7f7; color: #a64959; border: 1px solid #e8c5ca; border-radius: 11px; font-weight: 600; padding: 10px 14px; }
            QPushButton#cancelButton:hover:enabled { background: #ffeded; border-color: #d8949d; }
            QPushButton#cancelButton:disabled { background: #f5f6f9; color: #9aa8ba; border-color: #e0e5ed; }
            QFrame#tableFrame { background: transparent; border: 0; }
            QTableWidget { background: white; alternate-background-color: #f8faff; border: 0; gridline-color: transparent; selection-background-color: #e8f2ff; selection-color: #172b4d; outline: 0; }
            QWidget#bottomScrollbarGutter { background: #e6edf7; }
            QTableWidget::item { padding: 8px 9px; border-bottom: 1px solid #eaf0f7; }
            QTableWidget::item:selected { background: #e8f2ff; }
            QHeaderView { background: #edf3fb; }
            QHeaderView::section { background: #edf3fb; color: #61738d; border: 0; border-bottom: 1px solid #dce6f4; padding: 9px 9px 9px 16px; font-weight: 650; }
            QProgressBar { background: #e6edf7; border: 0; border-radius: 8px; min-height: 20px; max-height: 20px; text-align: center; color: #334968; font-size: 11px; font-weight: 650; }
            QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #35b7f2, stop:1 #147bea); border-radius: 8px; }
            QProgressBar#overallProgress::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #58cad0, stop:1 #2797be); border-radius: 8px; }
            QScrollBar:vertical { background: transparent; width: 16px; border: 0; }
            QScrollBar:horizontal { background: transparent; height: 16px; border: 0; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: 0; background: transparent; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; border: 0; background: transparent; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        """)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.itemChanged.connect(self.update_selection_count)
        self.restore_window_position()
        if self.migration_error:
            QTimer.singleShot(0, lambda: self.show_message("warning", self.t("Profile migration failed"),
                                                          self.migration_error))

    def t(self, key: str, **values) -> str:
        return tr(key, self.language, **values)

    def restore_window_position(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return
        saved = self.settings.value("window_position") if self.persist_state else None
        available = next((screen.availableGeometry() for screen in screens
                          if isinstance(saved, QPoint) and screen.availableGeometry().contains(saved)), None)
        if available is None:
            available = QGuiApplication.primaryScreen().availableGeometry()
            position = QPoint(
                available.x() + (available.width() - self.width()) // 2,
                available.y() + (available.height() - self.height()) // 2,
            )
        else:
            position = saved
        x = min(max(position.x(), available.left()), available.right() - self.width() + 1)
        y = min(max(position.y(), available.top()), available.bottom() - self.height() + 1)
        self.move(x, y)

    def closeEvent(self, event) -> None:
        if self.persist_state:
            self.settings.setValue("window_position", self.frameGeometry().topLeft())
        super().closeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_table_columns)

    def fit_table_columns(self) -> None:
        if self._table_columns_initialized:
            return
        width = self.table.viewport().width()
        if width <= 1000:
            return
        self.table.setColumnWidth(0, 84)
        self.table.setColumnWidth(1, 342)
        self.table.setColumnWidth(2, width - 84 - 342 - 208)
        self.table.setColumnWidth(3, 208)
        self._table_columns_initialized = True

    def language_changed(self, index: int) -> None:
        if 0 <= index < len(LANGUAGES):
            if self.persist_state:
                self.settings.setValue("language", LANGUAGES[index])
            self.show_message("information", self.t("Language saved"),
                              self.t("Restart the app to apply the selected language."))

    def show_message(self, kind: str, title: str, message: str) -> None:
        box = QMessageBox(self)
        style_light_dialog(box)
        box.setWindowTitle(title)
        box.setIcon({"information": QMessageBox.Icon.Information,
                     "warning": QMessageBox.Icon.Warning,
                     "critical": QMessageBox.Icon.Critical}[kind])
        box.setText(message)
        okay = CenteredTextButton(self.t("OK"), box)
        okay.setFixedHeight(44)
        box.addButton(okay, QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(okay)
        box.exec()

    def position_vertical_scrollbar(self) -> None:
        self.vertical_scrollbar.setGeometry(
            self.table_frame.width() - self.vertical_scrollbar.width() - 1,
            1,
            self.vertical_scrollbar.width(),
            max(0, self.table_frame.height() - 2),
        )
        self.table_overlay.raise_()

    def sync_vertical_scrollbar(self, minimum: int, maximum: int) -> None:
        scrollbar = self.vertical_scrollbar
        scrollbar.blockSignals(True)
        scrollbar.setRange(minimum, maximum)
        scrollbar.setPageStep(self.table_vertical_scrollbar.pageStep())
        scrollbar.setSingleStep(self.table_vertical_scrollbar.singleStep())
        scrollbar.setValue(self.table_vertical_scrollbar.value())
        scrollbar.blockSignals(False)

    def _sync_vertical_page_step(self) -> None:
        self.vertical_scrollbar.setPageStep(self.table_vertical_scrollbar.pageStep())
        self.vertical_scrollbar.setSingleStep(self.table_vertical_scrollbar.singleStep())

    @staticmethod
    def make_progress(format_text: str) -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setFormat(format_text)
        return bar

    @staticmethod
    def progress_row(label: str, bar: QProgressBar) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        title = QLabel(label)
        title.setMinimumWidth(105)
        title.setObjectName("progressRowTitle")
        row.addWidget(title)
        row.addWidget(bar, 1)
        return row

    @staticmethod
    def sender_icon() -> QIcon:
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        resource_candidates = (
            Path(__file__).resolve().parent / "assets" / "app-icon.svg",
            bundle_root / "assets" / "app-icon.svg",
            bundle_root.parent / "Resources" / "assets" / "app-icon.svg",
            Path(sys.executable).resolve().parent.parent / "Resources" / "assets" / "app-icon.svg",
        )
        icon_path = next((candidate for candidate in resource_candidates if candidate.is_file()), None)
        if icon_path is None:
            return QIcon()
        renderer = QSvgRenderer(str(icon_path))
        if not renderer.isValid():
            return QIcon()
        pixmap = QPixmap(256, 256)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, self.t("Select a folder with video/audio and subtitles"))
        if not chosen:
            return
        self.folder = Path(chosen)
        self.folder_label.setText(str(self.folder))
        self.scan()

    def scan(self) -> None:
        if self.folder is None:
            return
        try:
            self.groups, issues = scan_folder(self.folder, self.language)
        except (OSError, ValueError) as error:
            self.show_message("warning", self.t("Could not read the folder"),
                              localized_exception(error, self.language))
            return
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.groups))
        self.row_checks = []
        for row, group in enumerate(self.groups):
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, checkbox)
            self.table.setIconSize(QSize(44, 44))
            row_check = SelectionCheckBox()
            row_check.setChecked(len(self.groups) == 1)
            row_check.setText("")
            row_check.setFixedSize(38, 36)
            row_check.setCursor(Qt.CursorShape.PointingHandCursor)
            row_check.stateChanged.connect(self.update_selection_count)
            row_check.installEventFilter(self.scroll_wheel_forwarder)
            self.row_checks.append(row_check)
            check_cell = QWidget()
            check_cell.setObjectName("selectionCell")
            check_cell.setStyleSheet("QWidget#selectionCell { background: transparent; }")
            check_outer = QHBoxLayout(check_cell)
            check_outer.setContentsMargins(9, 7, 9, 7)
            check_outer.setSpacing(0)
            check_panel = CenteredSelectionPanel(row_check)
            check_outer.addWidget(check_panel)
            check_cell.installEventFilter(self.scroll_wheel_forwarder)
            self.table.setCellWidget(row, 0, check_cell)
            if self.table.rowHeight(row) < 76:
                self.table.setRowHeight(row, 76)
            kind = ("Video" if any(path.suffix.casefold() in {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi"}
                                   for path in group.media) else "Audio" if group.media else "Subtitle")
            name_item = QTableWidgetItem(group.name)
            name_item.setIcon(self.media_icon(kind))
            name_item.setToolTip(group.name)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, name_item)
            file_lines = "\n".join(f"{path.name}" for path in group.files)
            files_item = QTableWidgetItem(file_lines)
            files_item.setForeground(QColor("#61738d"))
            files_item.setToolTip(file_lines)
            files_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, files_item)
            total = sum(path.stat().st_size for path in group.files)
            self.set_row_status(row, self.format_size(total), "queued")
        self.fit_table_columns()
        self.table.resizeRowsToContents()
        for row in range(len(self.groups)):
            self.table.setRowHeight(row, min(120, max(76, self.table.rowHeight(row))))
        self.table.blockSignals(False)
        if issues:
            summary = "; ".join(issue.format(self.language) for issue in issues[:5])
            if len(issues) > 5:
                summary += self.t("; and ") + str(len(issues) - 5)
            self.status.setText(summary)
        elif self.groups:
            self.status.setText(self.t("Ready to review the media groups."))
        else:
            self.status.setText(self.t("No complete media groups found."))
        self.update_selection_count()

    def format_size(self, size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {self.t(unit)}"
            value /= 1024
        return f"{value:.1f} {self.t('GB')}"

    def set_row_status(self, row: int, size: str, status: str) -> None:
        palette = {
            "queued": ("#edf3fb", "#526783", "#8da0b8", "Queued"),
            "sending": ("#e8f2ff", "#176dcc", "#1680ed", "Uploading"),
            "sent": ("#e4f6ed", "#27704f", "#299866", "Sent"),
            "duplicate": ("#f1edff", "#684db0", "#8068cf", "Already in chat"),
            "error": ("#fff0ef", "#ad4d4a", "#d85e58", "Error"),
        }
        background, foreground, _dot, label = palette.get(status, palette["queued"])
        cell = QWidget()
        cell.setObjectName("statusCell")
        cell.setStyleSheet("QWidget#statusCell { background: transparent; }")
        outer = QHBoxLayout(cell)
        outer.setContentsMargins(8, 4, 14, 4)
        outer.setSpacing(8)
        size_label = QLabel(size)
        size_label.setObjectName("sizeValue")
        size_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        size_label.setStyleSheet("QLabel#sizeValue { color: #263a57; background: transparent; }")
        size_label.setMinimumWidth(0)
        badge = QLabel(self.t(label))
        badge.setObjectName("rowStatus")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"QLabel#rowStatus {{ color: {foreground}; background: {background}; "
            f"border-radius: 9px; padding: 3px 7px; font-size: 10px; font-weight: 650; }}"
        )
        outer.addWidget(size_label, 1)
        outer.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.table.setCellWidget(row, 3, cell)

    def set_group_status(self, name: str, status: str) -> None:
        for row, group in enumerate(self.groups):
            if group.name == name:
                cell = self.table.cellWidget(row, 3)
                size_label = cell.findChild(QLabel, "sizeValue") if cell else None
                self.set_row_status(row, size_label.text() if size_label else "", status)
                break

    @staticmethod
    def media_icon(kind: str) -> QIcon:
        size = 52
        scale = 3
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(4, 3, 48, 49)
        if kind == "Video":
            gradient.setColorAt(0, QColor("#75d4f5"))
            gradient.setColorAt(1, QColor("#3889df"))
        elif kind == "Subtitle":
            gradient.setColorAt(0, QColor("#a9cbed"))
            gradient.setColorAt(1, QColor("#5d91ce"))
        else:
            gradient.setColorAt(0, QColor("#76dfcb"))
            gradient.setColorAt(1, QColor("#168d9f"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(2, 2, size - 4, size - 4, 11, 11)
        if kind == "Video":
            painter.setPen(QPen(QColor("#ffffff"), 2.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(12, 14, 28, 24, 5, 5)
            play = QPainterPath()
            play.moveTo(22, 19)
            play.lineTo(33, 26)
            play.lineTo(22, 33)
            play.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ffffff"))
            painter.drawPath(play)
        elif kind == "Subtitle":
            painter.setPen(QPen(QColor("#ffffff"), 2.6, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(13, 10, 26, 32, 4, 4)
            for y in (20, 27, 34):
                painter.drawLine(19, y, 33, y)
        else:
            painter.setPen(QPen(QColor("#ffffff"), 3, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            for x, top, bottom in ((14, 24, 28), (20, 18, 34), (26, 13, 39), (32, 18, 34), (38, 24, 28)):
                painter.drawLine(x, top, x, bottom)
        painter.end()
        return QIcon(pixmap)

    def set_all_checks(self, state: Qt.CheckState) -> None:
        for checkbox in self.row_checks:
            checkbox.setChecked(state == Qt.CheckState.Checked)

    def selected_groups(self) -> list[Group]:
        return [group for row, group in enumerate(self.groups)
                if row < len(self.row_checks) and self.row_checks[row].isChecked()]

    def update_selection_count(self, *_args) -> None:
        selected = len(self.selected_groups()) if self.groups else 0
        self.selection_count.setText(self.t("Selected groups: {selected} of {total}", selected=selected, total=len(self.groups)))
        selected_background = QColor("#eaf4ff")
        default_background = QColor("#ffffff")
        for row in range(len(self.groups)):
            is_selected = row < len(self.row_checks) and self.row_checks[row].isChecked()
            for column in range(1, self.table.columnCount()):
                item = self.table.item(row, column)
                if item is not None:
                    item.setBackground(selected_background if is_selected else default_background)
            cell = self.table.cellWidget(row, 0)
            if cell is not None:
                panel = cell.findChild(QFrame, "selectionPanel")
                if panel is not None:
                    panel.setStyleSheet(
                        "QFrame#selectionPanel { background: #eaf4ff; border-radius: 12px; }"
                        if is_selected else
                        "QFrame#selectionPanel { background: white; border-radius: 12px; }"
                    )
            status_cell = self.table.cellWidget(row, 3)
            if status_cell is not None:
                panel = status_cell.findChild(QFrame, "statusPanel")
                if panel is not None:
                    panel.setStyleSheet(
                        "QFrame#statusPanel { background: #e2efff; border-radius: 11px; }"
                        if is_selected else
                        "QFrame#statusPanel { background: #eaf2fc; border-radius: 11px; }"
                    )
        self.send_button.setEnabled(selected > 0 and self.current_profile() is not None
                                    and self.chat_combo.currentIndex() >= 0 and self.worker is None)

    def load_chats(self) -> None:
        if self.worker is not None:
            return
        if self.current_profile() is None:
            self.status.setText(self.t("Add a Telegram profile before loading chats."))
            return
        self.set_busy(True, self.t("Loading available chats…"))
        self.worker = TelegramWorker(profile=self.current_profile(), profile_store=self.profile_store, language=self.language)
        self.worker.input_requested.connect(self.request_worker_input)
        self.worker.duplicate_check.connect(self.status.setText)
        self.worker.duplicate_review.connect(self.review_duplicates)
        self.worker.chats_ready.connect(self.chats_loaded)
        self.worker.cancelled.connect(self.operation_cancelled)
        self.worker.failed.connect(self.operation_failed)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def chats_loaded(self, chats) -> None:
        self.chat_entities = [row[1] for row in chats]
        self.chat_combo.clear()
        for row in chats:
            name, _entity = row[:2]
            photo = row[2] if len(row) > 2 else None
            self.chat_combo.addItem(self.chat_icon(name, photo), name)
        if chats:
            self.status.setText(self.t("Chats available for sending: {count}.", count=len(chats)))
        else:
            self.status.setText(self.t("No chats available with permission to send."))
        self.update_selection_count()

    @staticmethod
    def chat_icon(name: str, image_data: bytes | None) -> QIcon:
        size = 48
        scale = 3
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if image_data:
            avatar = QPixmap()
            if avatar.loadFromData(image_data):
                # Fit the complete source avatar inside the round mask instead of
                # enlarging and cutting off faces at the edges.
                diameter = size - 8
                avatar = avatar.scaled(diameter, diameter, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                base = QLinearGradient(3, 3, size - 3, size - 3)
                base.setColorAt(0, QColor("#dff1ff"))
                base.setColorAt(1, QColor("#b7d9f5"))
                painter.setBrush(base)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(2, 2, size - 4, size - 4)
                clip = QPainterPath()
                clip.addEllipse(4, 4, diameter, diameter)
                painter.setClipPath(clip)
                painter.drawPixmap((size - avatar.width()) // 2, (size - avatar.height()) // 2, avatar)
                painter.setClipping(False)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.drawEllipse(2, 2, size - 4, size - 4)
                painter.end()
                return QIcon(pixmap)
        palette = [("#55c6eb", "#2785de"), ("#68d6c2", "#158ea3"),
                   ("#a391f0", "#7057ce"), ("#f2a477", "#dd6a55"),
                   ("#79a9e8", "#4a77c2")]
        start, end = palette[sum(name.encode("utf-8")) % len(palette)]
        gradient = QLinearGradient(4, 4, 44, 44)
        gradient.setColorAt(0, QColor(start))
        gradient.setColorAt(1, QColor(end))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(1, 1, size - 2, size - 2)
        # Telegram-style group avatar: three simple people, kept legible at 30 px.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(19, 10, 10, 10)
        painter.drawEllipse(8, 15, 8, 8)
        painter.drawEllipse(32, 15, 8, 8)
        center_person = QPainterPath()
        center_person.moveTo(11, 38)
        center_person.cubicTo(12, 27, 17, 23, 24, 23)
        center_person.cubicTo(31, 23, 36, 27, 37, 38)
        center_person.closeSubpath()
        left_person = QPainterPath()
        left_person.moveTo(3, 35)
        left_person.cubicTo(4, 27, 7, 24, 12, 24)
        left_person.cubicTo(14, 24, 16, 25, 17, 27)
        left_person.cubicTo(14, 29, 12, 32, 11, 36)
        left_person.closeSubpath()
        right_person = QPainterPath()
        right_person.moveTo(45, 35)
        right_person.cubicTo(44, 27, 41, 24, 36, 24)
        right_person.cubicTo(34, 24, 32, 25, 31, 27)
        right_person.cubicTo(34, 29, 36, 32, 37, 36)
        right_person.closeSubpath()
        painter.drawPath(center_person)
        painter.drawPath(left_person)
        painter.drawPath(right_person)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(1, 1, size - 2, size - 2)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def profile_icon() -> QIcon:
        size = 48
        scale = 3
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(4, 4, 44, 44)
        gradient.setColorAt(0, QColor("#7abaf0"))
        gradient.setColorAt(1, QColor("#3976c7"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(1, 1, size - 2, size - 2)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(17, 9, 14, 14)
        shoulders = QPainterPath()
        shoulders.moveTo(9, 40)
        shoulders.cubicTo(10, 29, 16, 25, 24, 25)
        shoulders.cubicTo(32, 25, 38, 29, 39, 40)
        shoulders.closeSubpath()
        painter.drawPath(shoulders)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(1, 1, size - 2, size - 2)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def telegram_plane_icon() -> QIcon:
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plane = QPainterPath()
        plane.moveTo(3, 16)
        plane.cubicTo(2, 15, 3, 13, 5, 12)
        plane.lineTo(30, 4)
        plane.cubicTo(32, 3, 34, 4, 33, 7)
        plane.lineTo(27, 30)
        plane.cubicTo(26, 33, 24, 33, 22, 31)
        plane.lineTo(16, 26)
        plane.lineTo(12, 31)
        plane.cubicTo(11, 32, 10, 31, 10, 30)
        plane.lineTo(8, 21)
        plane.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawPath(plane)
        painter.end()
        return QIcon(pixmap)

    def send_selected(self) -> None:
        groups = self.selected_groups()
        index = self.chat_combo.currentIndex()
        if self.current_profile() is None or not groups or not 0 <= index < len(self.chat_entities):
            return
        target = self.chat_combo.currentText()
        names = "\n".join(f"• {group.name}" for group in groups[:8])
        if len(groups) > 8:
            names += "\n" + self.t("• … and {count} more groups", count=len(groups) - 8)
        extra_warning = (self.t("Some groups contain extra subtitles; every matching subtitle file will be sent.")
                         if any(group.has_extra_subtitles for group in groups) else "")
        confirmation, yes_button = self.send_confirmation_dialog(len(groups), target, names, extra_warning)
        confirmation.exec()
        if confirmation.clickedButton() is not yes_button:
            return
        self.set_busy(True, self.t("Connecting to Telegram…"))
        self.worker = TelegramWorker(groups=groups, target=self.chat_entities[index],
                                     profile=self.current_profile(), profile_store=self.profile_store, language=self.language)
        self.worker.input_requested.connect(self.request_worker_input)
        self.worker.duplicate_check.connect(self.status.setText)
        self.worker.duplicate_review.connect(self.review_duplicates)
        self.worker.progress.connect(self.status.setText)
        self.worker.task_progress.connect(self.update_task_progress)
        self.worker.completed.connect(self.sent)
        self.worker.cancelled.connect(self.operation_cancelled)
        self.worker.failed.connect(self.operation_failed)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def send_confirmation_dialog(self, group_count: int, target: str, names: str,
                                 extra_warning: str = ""):
        confirmation = QMessageBox(self)
        style_light_dialog(confirmation)
        confirmation.setWindowTitle(self.t("Upload confirmation"))
        confirmation.setIcon(QMessageBox.Icon.Question)
        confirmation.setText(self.t(
            "Send {count} group(s) to chat “{target}”?\n\n{names}\n\n{note}",
            count=group_count, target=target, names=names,
            note=self.t("Before sending, the app checks the chat history by file name and size. If it finds a match, it asks you to review the group first.")
            + ("\n\n" + extra_warning if extra_warning else "")))
        yes_button = CenteredTextButton(self.t("Yes"), confirmation)
        confirmation.addButton(yes_button, QMessageBox.ButtonRole.AcceptRole)
        cancel_button = CenteredTextButton(self.t("Cancel"), confirmation)
        confirmation.addButton(cancel_button, QMessageBox.ButtonRole.RejectRole)
        # QMessageBox applies slightly different native size hints to custom and
        # standard buttons on macOS. Use the same widget type and height so both
        # controls share one horizontal baseline without changing their widths.
        confirmation.ensurePolished()
        button_height = max(yes_button.sizeHint().height(), cancel_button.sizeHint().height())
        yes_button.setFixedHeight(button_height)
        cancel_button.setFixedHeight(button_height)
        confirmation.setDefaultButton(cancel_button)
        return confirmation, yes_button

    def reload_profiles(self) -> None:
        current = self.current_profile()["id"] if self.profiles and self.current_profile() else None
        self.profiles = self.profile_store.load()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for profile in self.profiles:
            self.profile_combo.addItem(self.profile_icon(), profile["name"])
        if current:
            index = next((i for i, row in enumerate(self.profiles) if row["id"] == current), -1)
            if index >= 0:
                self.profile_combo.setCurrentIndex(index)
        self.profile_combo.blockSignals(False)
        self.profile_combo.setEnabled(bool(self.profiles) and self.worker is None)
        self.refresh_chats_button.setEnabled(bool(self.profiles) and self.worker is None)
        if hasattr(self, "send_button"):
            self.profile_changed()

    def current_profile(self):
        index = self.profile_combo.currentIndex()
        return self.profiles[index] if 0 <= index < len(self.profiles) else None

    def profile_changed(self, *_args) -> None:
        self.chat_combo.clear()
        self.chat_entities = []
        self.update_selection_count()

    def manage_profiles(self) -> None:
        if self.worker is not None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("Telegram profiles"))
        style_light_dialog(dialog)
        dialog.setMinimumSize(500, 460)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(12)
        heading = QLabel(self.t("Telegram profiles"))
        heading.setStyleSheet("font-size: 18px; font-weight: 700; color: #173254;")
        layout.addWidget(heading)
        note = QLabel(self.t("Profiles stored by this app"))
        note.setStyleSheet("color: #617792;")
        layout.addWidget(note)
        listing = QListWidget()
        listing.setObjectName("profileList")
        layout.addWidget(listing, 1)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        add = dialog_button(self.t("Add…"), dialog)
        remove = dialog_button(self.t("Delete…"), dialog)
        close = dialog_button(self.t("Close"), dialog, default=True)
        actions.addWidget(add)
        actions.addWidget(remove)
        actions.addStretch(1)
        actions.addWidget(close)
        layout.addLayout(actions)

        def refresh(selected_id: str | None = None) -> None:
            listing.clear()
            for row in self.profiles:
                item = QListWidgetItem(self.profile_icon(), row["name"])
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                item.setSizeHint(QSize(0, 52))
                listing.addItem(item)
            desired = next((i for i, row in enumerate(self.profiles) if row["id"] == selected_id), 0)
            if self.profiles:
                listing.setCurrentRow(desired)
            remove.setEnabled(bool(self.profiles))

        def add_clicked() -> None:
            profile = self.add_profile()
            if profile:
                refresh(profile["id"])

        def remove_clicked() -> None:
            item = listing.currentItem()
            if item is None:
                return
            index = listing.currentRow()
            profile_id = item.data(Qt.ItemDataRole.UserRole)
            profile = next((row for row in self.profiles if row["id"] == profile_id), None)
            if profile is None or not self.confirm_profile_deletion(profile):
                return
            try:
                self.profile_store.delete(profile_id)
                self.reload_profiles()
            except (OSError, ValueError) as error:
                self.show_message("warning", self.t("Could not delete profile"),
                                  localized_exception(error, self.language))
                return
            next_index = min(index, len(self.profiles) - 1)
            if next_index >= 0:
                self.profile_combo.setCurrentIndex(next_index)
                refresh(self.profiles[next_index]["id"])
            else:
                refresh()
                self.status.setText(self.t("Add a Telegram profile before loading chats."))
            self.profile_changed()

        add.clicked.connect(add_clicked)
        remove.clicked.connect(remove_clicked)
        close.clicked.connect(dialog.accept)
        refresh(self.current_profile()["id"] if self.current_profile() else None)
        dialog.exec()

    def confirm_profile_deletion(self, profile: dict[str, str]) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("Delete Telegram profile"))
        style_light_dialog(dialog)
        dialog.setMinimumWidth(510)
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(0)
        content = QHBoxLayout()
        content.setSpacing(18)
        icon = QLabel()
        icon.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(56, 56))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        content.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        messages = QVBoxLayout()
        messages.setSpacing(8)
        question = QLabel(self.t("Delete profile “{name}” and its local session from this app?", name=profile["name"]))
        question.setWordWrap(True)
        question.setStyleSheet("font-size: 16px; font-weight: 700; color: #173254;")
        explanation = QLabel(self.t("Telegram messages, source media, and profiles in the old app remain unchanged."))
        explanation.setWordWrap(True)
        explanation.setStyleSheet("font-size: 15px; color: #1c2d49;")
        messages.addWidget(question)
        messages.addWidget(explanation)
        content.addLayout(messages, 1)
        outer.addLayout(content)
        outer.addSpacing(20)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)
        cancel = dialog_button(self.t("Cancel"), dialog, default=True)
        delete = dialog_button(self.t("Delete"), dialog)
        cancel.setMinimumWidth(108)
        delete.setMinimumWidth(108)
        actions.addWidget(cancel)
        actions.addWidget(delete)
        outer.addLayout(actions)
        cancel.clicked.connect(dialog.reject)
        delete.clicked.connect(dialog.accept)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def add_profile(self) -> dict[str, str] | None:
        if self.worker is not None:
            return None
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("New Telegram profile"))
        style_light_dialog(dialog)
        dialog.setMinimumWidth(530)
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(24, 24, 24, 22)
        outer.setSpacing(16)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(14)
        name = QLineEdit()
        phone = QLineEdit()
        api_id = QLineEdit()
        api_hash = QLineEdit()
        api_hash.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(self.t("Profile name"), name)
        form.addRow(self.t("Telegram phone number"), phone)
        form.addRow(self.t("API ID"), api_id)
        form.addRow(self.t("API Hash"), api_hash)
        note = QLabel(self.t("Get API ID and API Hash from my.telegram.org. The app will ask for your Telegram code and optional 2FA password separately. Only the authorized session is saved on this Mac."))
        note.setWordWrap(True)
        outer.addLayout(form)
        outer.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = dialog_button(self.t("Cancel"), dialog)
        save = dialog_button(self.t("Save"), dialog, default=True)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        outer.addLayout(buttons)
        cancel.clicked.connect(dialog.reject)
        save.clicked.connect(dialog.accept)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        try:
            profile = self.profile_store.add(name.text(), phone.text(), api_id.text(), api_hash.text())
        except (OSError, ValueError) as error:
            self.show_message("warning", self.t("Could not add profile"),
                              localized_exception(error, self.language))
            return None
        self.reload_profiles()
        self.profile_combo.setCurrentIndex(self.profiles.index(profile))
        return profile

    def request_worker_input(self, prompt, secret, context) -> None:
        event, answer = context
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("Sign in to Telegram"))
        style_light_dialog(dialog)
        dialog.setMinimumWidth(440)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        label = QLabel(prompt)
        label.setWordWrap(True)
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password if secret else QLineEdit.EchoMode.Normal)
        layout.addWidget(label)
        layout.addWidget(field)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = dialog_button(self.t("Cancel"), dialog)
        okay = dialog_button(self.t("OK"), dialog, default=True)
        actions.addWidget(cancel)
        actions.addWidget(okay)
        layout.addLayout(actions)
        cancel.clicked.connect(dialog.reject)
        okay.clicked.connect(dialog.accept)
        answer["value"] = field.text().strip() if dialog.exec() == QDialog.DialogCode.Accepted else ""
        event.set()

    def review_duplicates(self, duplicates, context) -> None:
        event, answer = context
        rows = []
        for group in duplicates[:12]:
            rows.append(f"• {group['name']}: {', '.join(group['files'])}")
        if len(duplicates) > 12:
            rows.append(self.t("• … and {count} more groups", count=len(duplicates) - 12))
        box = QMessageBox(self)
        style_light_dialog(box)
        box.setWindowTitle(self.t("Review possible duplicates"))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(self.t("The chat already contains files from these groups:"))
        box.setInformativeText("\n".join(rows) + "\n\n" + self.t("Duplicate matching uses file name and size. Spaces and underscores are treated as equal. You can skip complete groups, review manually, or send them again."))
        skip = box.addButton(self.t("Skip duplicates"), QMessageBox.ButtonRole.AcceptRole)
        send = box.addButton(self.t("Send anyway"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(self.t("Cancel — I will review"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(skip)
        box.exec()
        answer["choice"] = "skip" if box.clickedButton() is skip else "all" if box.clickedButton() is send else "cancel"
        event.set()

    def update_task_progress(self, data: dict) -> None:
        if "row_status" in data:
            name, status = data["row_status"]
            self.set_group_status(name, status)
        for name, status in data.get("row_statuses", {}).items():
            self.set_group_status(name, status)
        if not any(key in data for key in ("phase", "overall", "group", "file", "file_progress")):
            return
        self.stage_label.setText(data.get("phase", self.t("In progress…")))
        self.overall_progress.setValue(max(0, min(100, int(data.get("overall", 0)))))
        self.group_progress_label.setText(data.get("group_text", self.t("Group: —")))
        self.group_progress.setValue(max(0, min(100, int(data.get("group", 0)))))
        self.file_progress_label.setText(data.get("file", self.t("Current file")))
        self.file_progress.setValue(max(0, min(100, int(data.get("file_progress", 0)))))

    def sent(self, summary: str) -> None:
        self.status.setText(summary)
        self.show_message("information", self.t("Completed"), summary)

    def operation_cancelled(self, message: str) -> None:
        self.status.setText(message)
        self.stage_label.setText(message)

    def cancel_operation(self) -> None:
        if self.worker is None:
            return
        self.worker.request_cancel()
        self.cancel_button.setEnabled(False)
        self.status.setText(self.t("Stop after the current safe step…"))

    def operation_failed(self, message: str) -> None:
        self.status.setText(self.t("Cannot send"))
        self.show_message("critical", self.t("Could not complete the operation"), message)

    def set_busy(self, busy: bool, message: str) -> None:
        self.choose_folder_button.setEnabled(not busy)
        self.refresh_chats_button.setEnabled(not busy and bool(self.profiles))
        self.select_all_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)
        # Keep the table enabled so its scrollbars continue to work while
        # uploads are running. Lock only selection controls; the worker
        # already owns an immutable copy of the selected groups.
        self.table.setEnabled(True)
        for row_check in self.row_checks:
            row_check.setEnabled(not busy)
        self.chat_combo.setEnabled(not busy)
        self.profile_combo.setEnabled(not busy and bool(self.profiles))
        self.add_profile_button.setEnabled(not busy)
        self.send_button.setEnabled(not busy and self.current_profile() is not None
                                    and bool(self.selected_groups()) and self.chat_combo.currentIndex() >= 0)
        self.cancel_button.setEnabled(busy)
        self.status.setText(message)

    def worker_finished(self) -> None:
        self.worker = None
        self.set_busy(False, self.status.text())
        self.update_selection_count()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Telegram Media Sender")
    window = MediaSenderWindow()
    window.show()
    return app.exec()
