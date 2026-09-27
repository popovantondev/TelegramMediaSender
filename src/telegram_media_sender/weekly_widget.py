"""Qt UI for selecting weekly study material and reviewing its message order."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QThread, Signal, QFileSystemWatcher, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QHeaderView, QStyle, QStyleOptionViewItem, QStyledItemDelegate,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .i18n import tr
from .ui_design import (style_light_dialog, button_role, counted, format_size, STATUS_COLORS,
                        RoundedScrollBar, RoundedTableOverlay, themed_message)
from .weekly_journal import WeeklyJournal
from .publication_plan_import import (
    PublicationPlanImportError, load_publication_plan, revalidate_publication_item,
)
from .weekly_plan import (
    FileCategory, ItemKind, UploadMode, WeeklyScanResult, WeeklyUploadPlan,
    build_weekly_plan, scan_weekly_folder,
)


class _ScanThread(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            self.result.emit(scan_weekly_folder(self.path))
        except Exception as exc:
            self.failed.emit(str(exc))


class _PublicationPlanThread(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            self.loaded.emit(load_publication_plan(self.path))
        except Exception as exc:
            self.failed.emit(str(exc))


class _StatusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text:
            return super().paint(painter, option, index)
        base = QStyleOptionViewItem(option)
        self.initStyleOption(base, index)
        base.text = ""
        option.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, base, painter, option.widget)
        key = index.data(Qt.ItemDataRole.UserRole + 1) or "queued"
        background, foreground, _, _ = STATUS_COLORS.get(key, STATUS_COLORS["queued"])
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        bounds = option.rect.adjusted(8, 4, -8, -4)
        width = min(bounds.width(), painter.fontMetrics().horizontalAdvance(text) + 14)
        height = min(bounds.height(), 22)
        badge = QRectF(bounds.left(), bounds.center().y() - height / 2, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(badge, 9, 9)
        painter.setPen(QColor(foreground))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max(0, width - 14)))
        painter.restore()


class _CheckboxDelegate(QStyledItemDelegate):
    """Draw compact checkboxes with a visible tick on every supported theme."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        state = index.data(Qt.ItemDataRole.CheckStateRole)
        item_option = QStyleOptionViewItem(option)
        check_rect = None
        if state is not None and option.widget is not None:
            item_option.features |= QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
            check_rect = option.widget.style().subElementRect(
                QStyle.SubElement.SE_ItemViewItemCheckIndicator, item_option, option.widget
            )
        item_option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        super().paint(painter, item_option, index)
        if state is None or check_rect is None or check_rect.isEmpty():
            return

        # PySide exposes CheckStateRole as an int here, while Qt.CheckState is
        # an enum whose equality comparison with that int is false.
        checked = state == Qt.CheckState.Checked.value
        partial = state == Qt.CheckState.PartiallyChecked.value
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        fill = QColor("#1684e8") if checked else QColor("#8672cf") if partial else QColor("#ffffff")
        border = QColor("#1684e8") if checked else QColor("#8672cf") if partial else QColor("#aebfd3")
        if not enabled:
            fill.setAlpha(150)
            border.setAlpha(160)
        box = check_rect.adjusted(1, 1, -1, -1)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(fill)
        painter.drawRoundedRect(box, 4, 4)
        if checked:
            painter.setPen(QPen(QColor("#ffffff"), 2.0, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(box.left() + box.width() * 0.23, box.center().y(),
                             box.left() + box.width() * 0.43, box.bottom() - box.height() * 0.24)
            painter.drawLine(box.left() + box.width() * 0.43, box.bottom() - box.height() * 0.24,
                             box.right() - box.width() * 0.18, box.top() + box.height() * 0.23)
        elif partial:
            painter.setPen(QPen(QColor("#ffffff"), 2.0, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(box.left() + box.width() * 0.23, box.center().y(),
                             box.right() - box.width() * 0.23, box.center().y())
        painter.restore()


class WeeklyStudyWidget(QWidget):
    plan_ready = Signal(object)

    def __init__(self, language: str, settings, parent=None, data_dir: Path | None = None):
        super().__init__(parent)
        self.language = language
        self.settings = settings
        self.journal = WeeklyJournal(data_dir) if data_dir is not None else None
        self.scan: WeeklyScanResult | None = None
        self._scan_thread: _ScanThread | None = None
        self._building = False
        self._busy = False
        self._scan_manual = False
        self._watch_signature = None
        self._scan_start_signature = None
        self._scan_pending = False
        self.plan_stale = False
        self.plan_context_provider = None
        self.root: Path | None = None
        self.imported_plan: WeeklyUploadPlan | None = None
        self.imported_manifest_path: Path | None = None
        self._import_thread: _PublicationPlanThread | None = None
        self.week_checks: set[str] = set()
        self.day_checks: set[str] = set()
        self.week_material_checks: set[str] = set()
        self.setObjectName("weeklyStudyPage")
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._folder_changed)
        self.watcher.fileChanged.connect(self._folder_changed)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(600)
        self.refresh_timer.timeout.connect(self._check_folder_change)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 3)
        root.setSpacing(8)
        folder = QFrame()
        folder.setObjectName("surfaceCard")
        folder_outer = QVBoxLayout(folder)
        folder_outer.setContentsMargins(14, 9, 14, 11)
        folder_outer.setSpacing(5)
        title = QLabel(self.t("Source folder"))
        title.setObjectName("fieldTitle")
        folder_outer.addWidget(title)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        folder_outer.addLayout(folder_row)
        self.folder_label = QLabel()
        self.folder_label.setObjectName("folderPath")
        self.folder_label.setWordWrap(True)
        folder_row.addWidget(self.folder_label, 1)
        self.choose_button = QPushButton(self.t("Choose folder…"))
        self.refresh_button = QPushButton(self.t("Refresh"))
        self.import_button = QPushButton(self.t("Import publication plan…"))
        self.choose_button.clicked.connect(self.choose_folder)
        self.refresh_button.clicked.connect(self.refresh)
        self.import_button.clicked.connect(self.import_publication_plan)
        folder_row.addWidget(self.choose_button)
        folder_row.addWidget(self.refresh_button)
        folder_row.addWidget(self.import_button)
        root.addWidget(folder)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel(self.t("Select weeks and days")))
        toolbar.addStretch(1)
        self.summary = QLabel(self.t("No folder selected"))
        self.summary.setObjectName("selectionBadge")
        toolbar.addWidget(self.summary)
        self.select_all_button = QPushButton(self.t("Select all"))
        self.clear_button = QPushButton(self.t("Clear selection"))
        self.select_all_button.clicked.connect(lambda: self.set_all(True))
        self.clear_button.clicked.connect(lambda: self.set_all(False))
        toolbar.addWidget(self.select_all_button)
        toolbar.addWidget(self.clear_button)
        root.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setObjectName("weeklyTree")
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setItemDelegate(_CheckboxDelegate(self.tree))
        self.tree.setItemDelegateForColumn(3, _StatusDelegate(self.tree))
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([self.t("Week / materials"), self.t("Contents"),
                                   self.t("Size"), self.t("Status")])
        self.tree.setAlternatingRowColors(True)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.setUniformRowHeights(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(20)
        self.tree.setColumnWidth(1, 160)
        self.tree.setColumnWidth(2, 120)
        self.tree.setColumnWidth(3, 180)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree_frame = QFrame()
        self.tree_frame.setObjectName("weeklyTreeFrame")
        tree_layout = QVBoxLayout(self.tree_frame)
        tree_layout.setContentsMargins(1, 1, 1, 1)
        tree_layout.setSpacing(0)
        tree_layout.addWidget(self.tree)
        root.addWidget(self.tree_frame, 1)

        self.status = QLabel(self.t("Choose a folder with weekly materials."))
        self.status.setWordWrap(True)
        self.send_button = QPushButton(self.t("Check and send"))
        self.send_button.setObjectName("weeklySendButton")
        self.send_button.setEnabled(False)
        self._target_ready = False
        self.send_button.clicked.connect(self.review_plan)
        self.resume_button = QPushButton(self.t("Continue saved upload"))
        self.resume_button.setObjectName("secondaryButton")
        self.resume_button.clicked.connect(self.continue_saved_upload)
        self.resume_button.setVisible(False)
        self.footer = QHBoxLayout()
        self.footer.setSpacing(12)
        self.footer.addWidget(self.status, 1, Qt.AlignmentFlag.AlignVCenter)
        self.footer.addWidget(self.resume_button)
        self.footer.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(self.footer)

        last = self.settings.value("weekly/root")
        default = Path.home() / "Downloads" / "Учеба телеграм"
        initial = Path(last).expanduser() if last else default
        if initial.is_dir():
            self.set_root(initial)
        else:
            self.folder_label.setText(self.t("No folder selected"))
        self.refresh_resume_button()

    def format_size(self, value):
        return format_size(value, self.language)

    def t(self, key: str, **values) -> str:
        return tr(key, self.language, **values)

    def set_enabled(self, enabled: bool):
        self._busy = not enabled
        self.choose_button.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)
        self.import_button.setEnabled(enabled)
        self.select_all_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.send_button.setEnabled(enabled and self._target_ready and bool(
            self.imported_plan.items if self.imported_plan is not None
            else (self.selected_plan().items if self.scan is not None and not self.scan_blocked() else ())))
        self.resume_button.setEnabled(enabled and self._target_ready)
        self.tree.setEnabled(True)
        for index in range(self.tree.topLevelItemCount()):
            self._set_checkable(self.tree.topLevelItem(index), enabled)
        if enabled:
            self._update_summary()

    def set_target_ready(self, ready: bool):
        self._target_ready = bool(ready)
        self._update_summary()
        self.resume_button.setEnabled(not self._busy and self._target_ready)

    def _set_checkable(self, item, enabled: bool):
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key and (key.startswith("week:") or key.startswith("day:") or key.startswith("materials:")):
            flags = item.flags()
            if enabled:
                item.setFlags(flags | Qt.ItemFlag.ItemIsUserCheckable)
            else:
                item.setFlags(flags & ~Qt.ItemFlag.ItemIsUserCheckable)
        for index in range(item.childCount()):
            self._set_checkable(item.child(index), enabled)

    def scan_blocked(self) -> bool:
        if self.imported_plan is not None:
            return False
        return self.scan is None or any(n.blocking for n in self.scan.notices)

    def choose_folder(self):
        start = str(self.scan.root) if self.scan else str(Path.home() / "Downloads")
        selected = QFileDialog.getExistingDirectory(self, self.t("Choose folder…"), start)
        if selected:
            self.set_root(Path(selected))

    def set_root(self, path: Path, *, manual: bool = True):
        if manual:
            self.imported_plan = None
            self.imported_manifest_path = None
            self.select_all_button.setVisible(True)
            self.clear_button.setVisible(True)
        path = Path(path).expanduser()
        self.root = path
        if self._scan_thread is not None and self._scan_thread.isRunning():
            if manual:
                self._scan_pending = True
                self._scan_manual = True
                self.choose_button.setEnabled(False)
                self.refresh_button.setEnabled(False)
                self.import_button.setEnabled(False)
            return
        self._scan_start_signature = self._watch_signature
        self.settings.setValue("weekly/root", str(path))
        self.folder_label.setText(str(path))
        self._scan_manual = manual
        self._scan_thread = _ScanThread(path)
        self._scan_thread.result.connect(self._scan_ready)
        self._scan_thread.failed.connect(self._scan_failed)
        self._scan_thread.finished.connect(self._scan_finished)
        self._scan_thread.start()
        if manual:
            self.refresh_button.setEnabled(False)
            self.choose_button.setEnabled(False)
            self.import_button.setEnabled(False)
            self.status.setText(self.t("Scanning weekly folder…"))

    def refresh(self):
        if self.imported_plan is not None and self.imported_manifest_path is not None:
            self._read_publication_plan(self.imported_manifest_path)
            return
        if self.root is not None:
            self.set_root(self.root)

    def import_publication_plan(self):
        start = str(self.root or Path.home() / "Downloads")
        selected, _ = QFileDialog.getOpenFileName(
            self, self.t("Import publication plan…"), start,
            self.t("Publication plans (*.json);;JSON files (*.json)"))
        if selected:
            self._read_publication_plan(Path(selected))

    def _read_publication_plan(self, path: Path):
        if self._import_thread is not None and self._import_thread.isRunning():
            return
        self._import_path = Path(path).expanduser()
        self._import_thread = _PublicationPlanThread(self._import_path)
        self._import_thread.loaded.connect(self._publication_plan_loaded)
        self._import_thread.failed.connect(self._publication_plan_failed)
        self._import_thread.finished.connect(self._publication_plan_finished)
        self.import_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.status.setText(self.t("Validating publication plan and file checksums…"))
        self._import_thread.start()

    def _publication_plan_loaded(self, plan: WeeklyUploadPlan):
        if not self.confirm_plan(plan, {"import_preview": True}):
            self.status.setText(self.t("Publication plan preview cancelled."))
            return
        self.imported_plan = plan
        self.imported_manifest_path = self._import_path.resolve()
        self.root = plan.root
        self.scan = None
        self.week_checks.clear()
        self.day_checks.clear()
        self.week_material_checks.clear()
        self.folder_label.setText(self.t("Imported plan: {filename}",
                                         filename=self.imported_manifest_path.name))
        self.select_all_button.setVisible(False)
        self.clear_button.setVisible(False)
        self._reset_watcher()
        self._populate_imported_tree(plan)
        self.status.setText(self.t("Publication plan is ready: project {project}, revision {revision}",
                                   project=plan.publication_project_id,
                                   revision=plan.publication_revision))
        self._update_summary()

    def _publication_plan_failed(self, _detail: str):
        self.status.setText(self.t("Cannot import publication plan"))
        themed_message(self, "warning", self.t("Cannot import publication plan"),
                       self.t("The plan version, file paths, sizes, or checksums are invalid."))

    def _publication_plan_finished(self):
        self.import_button.setEnabled(not self._busy)
        self.refresh_button.setEnabled(not self._busy)

    def _populate_imported_tree(self, plan: WeeklyUploadPlan):
        self._building = True
        self.tree.clear()
        self.tree.setSortingEnabled(False)
        self.tree.setHeaderLabels([self.t("Publication order"), self.t("Type / date"),
                                   self.t("Size"), self.t("Status")])
        for item in plan.items:
            label = item.text if item.kind is ItemKind.TEXT else item.name or ""
            item_type = self.t("Text message") if item.kind is ItemKind.TEXT else self.t("File")
            size = self.format_size(item.size) if item.kind is ItemKind.FILE else ""
            location = item.week_key.split(":", 1)[-1]
            if item.day_key:
                location += " · " + item.day_key.rsplit("/", 1)[-1]
            row = QTreeWidgetItem([label, f"{item_type} · {location}", size, self.t("Waiting")])
            row.setToolTip(0, f"ID: {item.key}\n{item.relative_path or item.text or ''}")
            row.setData(0, Qt.ItemDataRole.UserRole, item.key)
            row.setData(3, Qt.ItemDataRole.UserRole, item.key)
            row.setData(3, Qt.ItemDataRole.UserRole + 1, "queued")
            self.tree.addTopLevelItem(row)
        self._building = False

    def _check_folder_change(self):
        if self.scan is None or self._busy:
            return
        signature = self._current_watch_signature()
        if signature == self._watch_signature:
            return
        if self._scan_thread is not None and self._scan_thread.isRunning():
            self._scan_pending = True
            return
        self.set_root(self.scan.root, manual=False)

    def _scan_finished(self):
        if self._scan_manual:
            self.choose_button.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self.import_button.setEnabled(True)
        self._scan_manual = False
        if self._scan_pending:
            self._scan_pending = False
            QTimer.singleShot(0, self._check_folder_change)

    def _scan_failed(self, message: str):
        self.scan = None
        self.tree.clear()
        self.week_checks.clear()
        self.day_checks.clear()
        self.week_material_checks.clear()
        self._reset_watcher()
        self.status.setText(self.t("Could not read the folder") + f": {message}")
        self.summary.setText(self.t(
            "Selected: {selection} · {size}",
            selection=f"{counted(0, 'week', self.language)} · {counted(0, 'day', self.language)}",
            size=self.format_size(0)))
        self.send_button.setEnabled(False)

    def _scan_ready(self, scan: WeeklyScanResult):
        old_weeks, old_days, old_materials = set(self.week_checks), set(self.day_checks), set(self.week_material_checks)
        first_scan = self.scan is None
        old_week_keys = {w.key for w in self.scan.weeks} if self.scan else set()
        old_day_keys = {d.key for w in self.scan.weeks for d in w.days} if self.scan else set()
        old_material_keys = {w.key for w in self.scan.weeks if w.week_files} if self.scan else set()
        self.scan = scan
        week_keys = {week.key for week in scan.weeks}
        day_keys = {day.key for week in scan.weeks for day in week.days}
        material_keys = {week.key for week in scan.weeks if week.week_files}
        self.week_checks = old_weeks & week_keys
        self.day_checks = old_days & day_keys
        self.week_material_checks = old_materials & material_keys
        if first_scan:
            self.week_checks = set(week_keys)
            self.day_checks = set(day_keys)
            self.week_material_checks = set(material_keys)
        else:
            # Newly discovered entries default to selected. Existing entries retain choice.
            self.week_checks |= week_keys - old_week_keys
            self.day_checks |= day_keys - old_day_keys
            self.week_material_checks |= material_keys - old_material_keys
        self._populate_tree()
        self._reset_watcher()
        self._watch_signature = self._current_watch_signature()
        if self._scan_start_signature is not None and self._watch_signature != self._scan_start_signature:
            self._scan_pending = True
        self._scan_start_signature = self._watch_signature
        message = self.t("Scan complete: {weeks} weeks, {days} days", weeks=len(scan.weeks),
                         days=sum(len(w.days) for w in scan.weeks))
        if scan.notices:
            message += f" · {self.t('Problems')}: {len(scan.notices)}"
        if scan.excluded:
            message += f" · {self.t('Excluded hidden files')}: {len(scan.excluded)}"
        self.status.setText(message)
        self._update_summary()
        self.send_button.setEnabled(self._target_ready and not self.scan_blocked()
                                    and bool(self.selected_plan().items) and not self._busy)

    def _reset_watcher(self):
        directories, files = set(), set()
        if self.scan is not None:
            directories = {self.scan.root}
            directories.update(w.path for w in self.scan.weeks)
            directories.update(d.path for w in self.scan.weeks for d in w.days)

            def add_descendant_parents(file_path: Path):
                # Parent folders above the chosen root are unrelated and can
                # generate constant macOS watcher notifications (for example,
                # from Downloads or the user's home folder).
                for parent in file_path.parents:
                    if parent == self.scan.root:
                        break
                    if self.scan.root in parent.parents:
                        directories.add(parent)

            for week in self.scan.weeks:
                for file in week.week_files:
                    add_descendant_parents(file.path)
                for day in week.days:
                    for file in day.files:
                        add_descendant_parents(file.path)
            files = {file.path for week in self.scan.weeks
                     for file in [*week.week_files, *(f for day in week.days for f in day.files)]}
        directories = {str(path) for path in directories if path.is_dir() and not path.is_symlink()}
        files = {str(path) for path in files if path.is_file() and not path.is_symlink()}
        old_dirs, old_files = set(self.watcher.directories()), set(self.watcher.files())
        remove = (old_dirs - directories) | (old_files - files)
        add = (directories - old_dirs) | (files - old_files)
        if remove:
            self.watcher.removePaths(sorted(remove))
        if add:
            self.watcher.addPaths(sorted(add))

    def _current_watch_signature(self):
        """Cheap metadata snapshot to discard duplicate watcher notifications."""
        entries = []
        for raw_dir in self.watcher.directories():
            folder = Path(raw_dir)
            try:
                children = sorted(folder.iterdir(), key=lambda child: child.name.casefold())
            except OSError:
                entries.append((raw_dir, "unavailable"))
                continue
            for child in children:
                if child.name == ".DS_Store" or child.name.startswith("._") or "__MACOSX" in child.parts:
                    continue
                try:
                    info = child.lstat()
                    entries.append((str(child), info.st_mode, info.st_size, info.st_mtime_ns))
                except OSError:
                    entries.append((str(child), "unavailable"))
        for raw_file in self.watcher.files():
            try:
                info = Path(raw_file).stat()
                entries.append((raw_file, info.st_size, info.st_mtime_ns))
            except OSError:
                entries.append((raw_file, "unavailable"))
        return tuple(sorted(entries))

    def _folder_changed(self, _path: str):
        if self._busy:
            self.plan_stale = True
            self.status.setText(self.t("Folder changed during upload; the active queue is unchanged."))
            return
        self.refresh_timer.start()

    def finish_work(self):
        self._busy = False
        if self.plan_stale:
            self.plan_stale = False
            answer = themed_message(self, "question", self.t("Folder changed"),
                                          self.t("The folder changed during upload. Refresh it now?"),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.Yes)
            if answer == QMessageBox.StandardButton.Yes:
                self.refresh()

    def _populate_tree(self):
        assert self.scan is not None
        self._building = True
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        plan_items = self.selected_plan().items
        self._planned_items = {item.key for item in plan_items}
        self._planned_file_keys = {item.key for item in plan_items if item.kind is ItemKind.FILE}
        self._planned_week_keys = {item.week_key for item in plan_items}
        self._planned_day_keys = {item.day_key for item in plan_items if item.day_key}
        for week in self.scan.weeks:
            week_active = week.key in self._planned_week_keys
            week_item = self._node(week.name, counted(len(week.days), "day", self.language),
                                   self.format_size(sum(f.size for f in week.week_files) +
                                                sum(f.size for d in week.days for f in d.files)),
                                   self.t("Waiting") if week_active else "",
                                   key=week.key, checkable=True)
            self.tree.addTopLevelItem(week_item)
            if week.week_files:
                material = self._node(self.t("Week materials"), _file_count(len(week.week_files), self.language),
                                      self.format_size(sum(f.size for f in week.week_files)),
                                      self.t("Waiting") if any(f.key in self._planned_file_keys
                                                                for f in week.week_files) else "",
                                      key=f"materials:{week.key}", checkable=True)
                week_item.addChild(material)
                for file in week.week_files:
                    material.addChild(self._node(file.name, self.t(_category_label(file.category)), self.format_size(file.size),
                                                 self.t("Waiting") if file.key in self._planned_file_keys else "",
                                                 key=file.key, path=file.relative_path))
                material.setCheckState(0, Qt.CheckState.Checked if week.key in self.week_material_checks
                                       else Qt.CheckState.Unchecked)
            for day in week.days:
                day_item = self._node(day.day.isoformat(), _file_count(len(day.files), self.language),
                                      self.format_size(sum(f.size for f in day.files)),
                                      self.t("Waiting") if day.key in self._planned_day_keys else "",
                                      key=day.key, checkable=True)
                week_item.addChild(day_item)
                for category in FileCategory:
                    files = [f for f in day.files if f.category is category]
                    if not files:
                        continue
                    category_item = QTreeWidgetItem([self.t(_category_label(category)),
                                                     _file_count(len(files), self.language),
                                                     self.format_size(sum(f.size for f in files)), ""])
                    category_item.setFlags(category_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    day_item.addChild(category_item)
                    for file in files:
                        category_item.addChild(self._node(file.name, self.t(_category_label(category)),
                                                          self.format_size(file.size),
                                                          self.t("Waiting") if file.key in self._planned_file_keys else "",
                                                          key=file.key, path=file.relative_path))
                day_item.setCheckState(0, Qt.CheckState.Checked if day.key in self.day_checks
                                       else Qt.CheckState.Unchecked)
            selectable_children = [week_item.child(i) for i in range(week_item.childCount())
                                   if week_item.child(i).data(0, Qt.ItemDataRole.UserRole)]
            checked_children = sum(child.checkState(0) == Qt.CheckState.Checked for child in selectable_children)
            week_state = (Qt.CheckState.Checked if selectable_children and checked_children == len(selectable_children)
                          else Qt.CheckState.PartiallyChecked if checked_children or
                          any(child.checkState(0) == Qt.CheckState.PartiallyChecked for child in selectable_children)
                          else Qt.CheckState.Unchecked)
            week_item.setCheckState(0, week_state)
            week_item.setExpanded(True)
        self.tree.setUpdatesEnabled(True)
        self._building = False

    def _node(self, name, contents, size, status, *, key=None, path=None, checkable=False):
        status = self.t("Queued") if status == self.t("Waiting") else status
        item = QTreeWidgetItem([name, contents, size, status])
        item.setData(3, Qt.ItemDataRole.UserRole, key or "")
        initial_status = "queued" if status else "idle"
        item.setData(3, Qt.ItemDataRole.UserRole + 1, initial_status)
        item.setData(3, Qt.ItemDataRole.UserRole + 2, initial_status)
        item.setToolTip(3, status)
        item.setToolTip(0, path or name)
        if key:
            item.setData(0, Qt.ItemDataRole.UserRole, key)
        if checkable:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            selected = (key in self.week_checks if key and key.startswith("week:") else
                        key in self.day_checks if key and key.startswith("day:") else
                        key.removeprefix("materials:") in self.week_material_checks)
            item.setCheckState(0, Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
        return item

    def update_item_status(self, item_key: str, status: str):
        """Refresh the matching plan row and its week/day aggregate badges."""
        if item_key.startswith("header:"):
            item_key = item_key.removeprefix("header:")
        if status == "pending":
            status = "queued"
        if status == "skipped":
            status = "duplicate"

        def apply(item, state, *, direct=False):
            label = STATUS_COLORS.get(state, STATUS_COLORS["queued"])[3]
            item.setText(3, self.t(label))
            item.setData(3, Qt.ItemDataRole.UserRole + 1, state)
            if direct:
                item.setData(3, Qt.ItemDataRole.UserRole + 2, state)
            item.setToolTip(3, self.t(label))

        def visit(item):
            key = item.data(0, Qt.ItemDataRole.UserRole)
            if key == item_key:
                apply(item, status, direct=True)
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))

        def aggregate(item):
            key = item.data(0, Qt.ItemDataRole.UserRole) or ""
            child_states = descendants(item)
            if key.startswith("week:") or key.startswith("day:") or key.startswith("materials:"):
                direct_state = item.data(3, Qt.ItemDataRole.UserRole + 2) or "queued"
                if direct_state not in {"queued", "idle"}:
                    child_states.append(direct_state)
                if not child_states:
                    return "idle"
                if "error" in child_states:
                    state = "error"
                elif "uncertain" in child_states:
                    state = "uncertain"
                elif "sending" in child_states:
                    state = "sending"
                elif all(state in {"sent", "duplicate"} for state in child_states):
                    state = child_states[0] if len(set(child_states)) == 1 else "partial"
                elif any(state in {"sent", "duplicate", "partial"} for state in child_states):
                    state = "partial"
                else:
                    state = "queued"
                apply(item, state)
            return item.data(3, Qt.ItemDataRole.UserRole + 1) or "queued"

        # Category rows are structural and have no plan key; include their
        # descendants when deriving day and week states.
        def descendants(item):
            result = []
            for index in range(item.childCount()):
                child = item.child(index)
                if child.data(0, Qt.ItemDataRole.UserRole):
                    state = aggregate(child)
                    if state != "idle":
                        result.append(state)
                else:
                    result.extend(descendants(child))
            return result

        for index in range(self.tree.topLevelItemCount()):
            week = self.tree.topLevelItem(index)
            children = descendants(week)
            direct_state = week.data(3, Qt.ItemDataRole.UserRole + 2) or "idle"
            if direct_state not in {"queued", "idle"}:
                children.append(direct_state)
            if not children:
                continue
            if "error" in children:
                state = "error"
            elif "uncertain" in children:
                state = "uncertain"
            elif "sending" in children:
                state = "sending"
            elif all(s in {"sent", "duplicate"} for s in children):
                state = children[0] if len(set(children)) == 1 else "partial"
            elif any(s in {"sent", "duplicate", "partial"} for s in children):
                state = "partial"
            else:
                state = "queued"
            apply(week, state)

    def _item_changed(self, item, column):
        if self._building or column != 0:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if not key:
            return
        checked = item.checkState(0) == Qt.CheckState.Checked
        if key.startswith("week:"):
            if checked:
                self.week_checks.add(key)
                week = next((w for w in self.scan.weeks if w.key == key), None)
                if week:
                    self.day_checks.update(d.key for d in week.days)
                    if week.week_files:
                        self.week_material_checks.add(key)
            elif item.checkState(0) == Qt.CheckState.Unchecked:
                self.week_checks.discard(key)
                week = next((w for w in self.scan.weeks if w.key == key), None)
                if week:
                    self.day_checks.difference_update(d.key for d in week.days)
                    self.week_material_checks.discard(key)
            else:
                # A parent becomes partially checked when a single child is changed.
                self.week_checks.add(key)
            self._building = True
            for index in range(item.childCount()):
                child = item.child(index)
                child_key = child.data(0, Qt.ItemDataRole.UserRole)
                if child_key:
                    child.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self._building = False
        elif key.startswith("day:"):
            (self.day_checks.add if checked else self.day_checks.discard)(key)
            self._sync_week_checkbox(item.parent())
        elif key.startswith("materials:"):
            week_key = key.removeprefix("materials:")
            (self.week_material_checks.add if checked else self.week_material_checks.discard)(week_key)
            self._sync_week_checkbox(item.parent())
        self._update_summary()

    def _sync_week_checkbox(self, week_item):
        if week_item is None:
            return
        children = [week_item.child(i) for i in range(week_item.childCount())
                    if week_item.child(i).data(0, Qt.ItemDataRole.UserRole)]
        selected = sum(child.checkState(0) == Qt.CheckState.Checked for child in children)
        state = (Qt.CheckState.Checked if children and selected == len(children)
                 else Qt.CheckState.PartiallyChecked if selected or
                 any(child.checkState(0) == Qt.CheckState.PartiallyChecked for child in children)
                 else Qt.CheckState.Unchecked)
        self._building = True
        week_item.setCheckState(0, state)
        self._building = False

    def _update_summary(self):
        if self.imported_plan is not None:
            plan = self.imported_plan
            self.summary.setText(self.t("Imported {items} messages · {size}",
                                        items=counted(plan.message_count, "message", self.language),
                                        size=self.format_size(plan.total_bytes)))
            self.send_button.setEnabled(not self._busy and self._target_ready and bool(plan.items))
            return
        if not self.scan:
            return
        plan = self.selected_plan()
        chosen_weeks = sum(w.key in self.week_checks for w in self.scan.weeks)
        chosen_days = sum(d.key in self.day_checks for w in self.scan.weeks for d in w.days)
        self.summary.setText(self.t("Selected: {selection} · {size}",
                                   selection=f"{counted(chosen_weeks, 'week', self.language)} · {counted(chosen_days, 'day', self.language)}",
                                   size=self.format_size(plan.total_bytes)))
        self.send_button.setEnabled(not self._busy and self._target_ready
                                    and not self.scan_blocked() and bool(plan.items))

    def selected_plan(self, **target) -> WeeklyUploadPlan:
        if self.imported_plan is not None:
            return self.imported_plan
        if self.scan is None:
            raise ValueError("No weekly folder has been scanned")
        return build_weekly_plan(self.scan, self.week_checks, self.day_checks,
                                 self.week_material_checks, **target)

    def set_all(self, selected: bool):
        if self.imported_plan is not None:
            return
        if not self.scan:
            return
        if selected:
            self.week_checks = {w.key for w in self.scan.weeks}
            self.day_checks = {d.key for w in self.scan.weeks for d in w.days}
            self.week_material_checks = {w.key for w in self.scan.weeks if w.week_files}
        else:
            self.week_checks.clear()
            self.day_checks.clear()
            self.week_material_checks.clear()
        self._populate_tree()
        self._update_summary()

    def review_plan(self):
        target = self.plan_context_provider() if self.plan_context_provider else {}
        plan = self.selected_plan(**target)
        self.plan_ready.emit(plan)

    def refresh_resume_button(self):
        if self.journal is None:
            self.resume_button.setVisible(False)
            return
        try:
            self._unfinished = self.journal.latest_unfinished_plan()
        except Exception:
            self._unfinished = None
        if self._unfinished is None:
            self.resume_button.setVisible(False)
            return
        plan = self._unfinished["plan"]
        self.resume_button.setText(self.t("Continue saved upload · {chat} · {count} items",
                                          chat=plan.chat_title or self.t("Unknown chat"),
                                          count=self._unfinished["pending"]))
        self.resume_button.setVisible(True)
        self.resume_button.setEnabled(not self._busy and self._target_ready)

    def continue_saved_upload(self):
        self.refresh_resume_button()
        if self._unfinished is not None:
            self.plan_ready.emit(self._unfinished["plan"])

    def confirm_plan(self, plan: WeeklyUploadPlan, report: dict | None = None) -> bool:
        report = report or {}
        import_preview = bool(report.get("import_preview"))
        dialog = QDialog(self)
        style_light_dialog(dialog)
        dialog.setWindowTitle(self.t("Preview publication plan") if import_preview
                              else self.t("Review upload plan"))
        dialog.setObjectName("weeklyPlanDialog")
        dialog.setMinimumSize(760, 620)
        layout = QVBoxLayout(dialog)
        title = QLabel(self.t("Preview publication plan") if import_preview
                       else self.t("Review upload plan"))
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        banner = QLabel()
        banner.setObjectName("secondaryNote")
        banner.setTextFormat(Qt.TextFormat.RichText)
        from html import escape
        if import_preview:
            banner.setText(self.t("Publication plan: project {project}, revision {revision}",
                                  project=escape(plan.publication_project_id),
                                  revision=plan.publication_revision))
        else:
            if plan.mode is UploadMode.MEDIA_GROUPS:
                selection = counted(len({item.group_key for item in plan.items}), "group", self.language)
            elif plan.mode is UploadMode.PUBLICATION_PLAN:
                selection = counted(len(plan.items), "message", self.language)
            else:
                selection = f"{counted(len({item.week_key for item in plan.items}), 'week', self.language)}, {counted(len({item.day_key for item in plan.items if item.day_key}), 'day', self.language)}"
            banner.setText(self.t("<b>Profile:</b> {profile} · <b>Chat:</b> {chat} · <b>Selected:</b> {selection}",
                                  profile=escape(target_or_placeholder(plan.profile_id)),
                                  chat=escape(target_or_placeholder(plan.chat_title)), selection=selection))
        banner.setWordWrap(True)
        layout.addWidget(banner)
        layout.addWidget(QLabel(self.t("To send: {messages}, {files}, {size}",
                                       messages=counted(report.get("pending", plan.message_count), "message", self.language),
                                       files=counted(report.get("pending_files", plan.file_count), "file", self.language),
                                       size=self.format_size(report.get("pending_bytes", plan.total_bytes)))))
        if report.get("found_in_chat"):
            layout.addWidget(QLabel(self.t("Already found in chat: {count}",
                                           count=report["found_in_chat"])))
        view = QTreeWidget()
        view.setObjectName("planTree")
        view.setVerticalScrollBar(RoundedScrollBar(Qt.Orientation.Vertical, view))
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setHeaderLabels([self.t("Upload order"), self.t("Type / size")])
        view.header().setStretchLastSection(False)
        view.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        view.setColumnWidth(1, 190)
        view.setAlternatingRowColors(True)
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        if plan.publication_project_id:
            _populate_publication_preview_tree(view, plan, self.language)
        else:
            _populate_plan_tree(view, plan, self.language)
        view.expandAll()
        frame = QFrame()
        frame.setObjectName("planFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(1, 1, 1, 1)
        frame_layout.addWidget(view)
        layout.addWidget(frame, 1)
        overlay = RoundedTableOverlay(frame)
        actions = QHBoxLayout()
        actions.addStretch(1)
        back = QPushButton(self.t("Back"))
        start = QPushButton(self.t("Use this plan") if import_preview else self.t("Start upload"))
        button_role(start)
        back.clicked.connect(dialog.reject)
        start.clicked.connect(dialog.accept)
        actions.addWidget(back)
        actions.addWidget(start)
        layout.addLayout(actions)
        return dialog.exec() == QDialog.DialogCode.Accepted


def _populate_plan_tree(view: QTreeWidget, plan: WeeklyUploadPlan, language: str):
    week_nodes = {}
    day_nodes = {}
    category_nodes = {}
    for item in plan.items:
        week = week_nodes.get(item.week_key)
        if week is None:
            week = QTreeWidgetItem([item.week_key.split(":", 1)[-1], ""])
            week.setExpanded(True)
            view.addTopLevelItem(week)
            week_nodes[item.week_key] = week
        if item.kind is ItemKind.TEXT:
            if item.day_key:
                node = QTreeWidgetItem([item.text or "", tr("Text message", language)])
                week.addChild(node)
                node.setExpanded(True)
                day_nodes[item.day_key] = node
            else:
                week.setText(0, item.text or week.text(0))
                week.setText(1, tr("Text message", language))
            continue
        parent = day_nodes.get(item.day_key) if item.day_key else week
        if item.category:
            category_key = (item.week_key, item.day_key, item.category)
            if category_key not in category_nodes:
                category = QTreeWidgetItem([tr(_category_label(item.category), language), ""])
                parent.addChild(category)
                category.setExpanded(True)
                category_nodes[category_key] = category
            parent = category_nodes[category_key]
        entry = QTreeWidgetItem([item.name or item.text or "", format_size(item.size, language)])
        entry.setToolTip(0, item.relative_path or item.name or "")
        parent.addChild(entry)


def _populate_publication_preview_tree(view: QTreeWidget, plan: WeeklyUploadPlan, language: str):
    """Render imported items as a flat ordered list; never regroup or sort them."""
    view.setSortingEnabled(False)
    for item in plan.items:
        label = item.text if item.kind is ItemKind.TEXT else item.name or ""
        kind = tr("Text message" if item.kind is ItemKind.TEXT else "File", language)
        location = item.week_key.split(":", 1)[-1]
        if item.day_key:
            location += " · " + item.day_key.rsplit("/", 1)[-1]
        details = f"{kind} · {location}"
        if item.kind is ItemKind.FILE:
            details += " · " + format_size(item.size, language)
        row = QTreeWidgetItem([label, details])
        row.setToolTip(0, f"ID: {item.key}\n{item.relative_path or item.text or ''}")
        view.addTopLevelItem(row)


def _category_label(category: FileCategory) -> str:
    return {
        FileCategory.WEEK_MATERIALS: "Week materials",
        FileCategory.AUDIO_VIDEO: "Audio and video",
        FileCategory.SUBTITLES: "Subtitles",
        FileCategory.SCREENSHOTS: "Screenshots",
        FileCategory.EXTRA_MATERIALS: "Additional materials",
        FileCategory.OTHER: "Other materials",
    }[category]


def _format_size(value: int) -> str:
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.1f} {unit}" if unit not in {"B", "KB"} else f"{int(number)} {unit}"
        number /= 1024
    return f"{value} B"


def _file_count(count: int, language: str) -> str:
    if language == "ru":
        last_two = count % 100
        last = count % 10
        if last == 1 and last_two != 11:
            key = "{count} file"
        elif 2 <= last <= 4 and not 12 <= last_two <= 14:
            key = "{count} files few"
        else:
            key = "{count} files"
    else:
        key = "{count} file" if count == 1 else "{count} files"
    return tr(key, language, count=count)


def target_or_placeholder(value: str) -> str:
    return value or "—"
