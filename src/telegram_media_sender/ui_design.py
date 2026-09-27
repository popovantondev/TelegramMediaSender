"""Shared appearance and presentation helpers for the desktop UI."""
from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, QEvent
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPalette, QPixmap, QFont
from PySide6.QtWidgets import QWidget, QTableWidget, QScrollBar, QDialog, QMessageBox
from .i18n import tr

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
            track = QRectF(6, 4, max(0, self.width() - 8), max(0, self.height() - 8))
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



def style_light_dialog(dialog: QDialog) -> None:
    parent = dialog.parentWidget()
    dialog.language = getattr(parent, "language", "en")
    dialog.setPalette(light_palette())
    dialog.setStyleSheet("""
        QDialog, QMessageBox { background: #f3f6fc; color: #1c2d49; font-size: 13px; }
        QMessageBox QLabel#qt_msgbox_label, QMessageBox QLabel#qt_msgbox_informativelabel { min-width: 320px; }
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
    """ + BUTTON_STYLES + COMMON_STYLES)



BUTTON_STYLES = """
QPushButton[role="primary"] { background: #147bea; color: white; border: 1px solid #147bea; border-radius: 9px; padding: 8px 14px; }
QPushButton[role="primary"]:hover { background: #096bd5; border-color: #096bd5; }
QPushButton[role="danger"] { background: #fff0ef; color: #a93732; border: 1px solid #edb7b2; border-radius: 9px; padding: 8px 14px; }
QPushButton[role="danger"]:hover { background: #ffe2df; }
QPushButton[role="primary"]:disabled, QPushButton[role="danger"]:disabled { background: #edf1f7; color: #718399; border-color: #d5dfed; }
"""
COMMON_STYLES = """
QLabel#dialogTitle { font-size: 18px; font-weight: 700; color: #173254; }
QLabel#secondaryNote { font-size: 13px; color: #536782; font-weight: 400; }
QTableWidget#planTable { background: white; alternate-background-color: #f8faff; border: 0; outline: 0; }
QTableWidget#planTable::item { padding: 7px 8px; border-bottom: 1px solid #eaf0f7; }
QLabel#emptyState { color: #65758f; font-size: 13px; padding: 12px; }
QTreeWidget#planTree { background: white; alternate-background-color: #f8faff; border: 0; outline: 0; }
QTreeWidget#planTree::item { padding: 7px 8px; border-bottom: 1px solid #eaf0f7; }
QTreeWidget#planTree::item:selected { background: #e8f2ff; color: #172b4d; }
QHeaderView::section { background: #edf3fb; color: #61738d; border: 0; border-bottom: 1px solid #dce6f4; padding: 9px 9px 9px 16px; font-weight: 650; }
QFrame#planFrame { background: white; border: 1px solid #dce6f4; border-radius: 13px; }
QRadioButton { spacing: 8px; padding: 4px 0; }
QScrollBar:vertical { background: #e6edf7; width: 16px; border: 0; margin: 0; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

STATUS_COLORS = {
    'queued': ('#edf3fb', '#526783', '#8da0b8', 'Queued'),
    'sending': ('#e8f2ff', '#176dcc', '#1680ed', 'Uploading'),
    'sent': ('#e4f6ed', '#27704f', '#299866', 'Sent'),
    'duplicate': ('#f1edff', '#684db0', '#8068cf', 'Already in chat'),
    'partial': ('#fff5e5', '#946319', '#d29a37', 'Partially sent'),
    'uncertain': ('#fff5e5', '#946319', '#d29a37', 'Check chat'),
    'error': ('#fff0ef', '#ad4d4a', '#d85e58', 'Error'),
}

def button_role(button, role='primary'):
    button.setProperty('role', role)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def format_size(value, language='en'):
    number = float(value)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if number < 1024 or unit == 'TB':
            text = f'{number:.1f}'
            if language in ('ru', 'de'):
                text = text.replace('.', ',')
            labels = {'ru': {'B': 'Б', 'KB': 'КБ', 'MB': 'МБ', 'GB': 'ГБ', 'TB': 'ТБ'}}
            return f"{text} {labels.get(language, {}).get(unit, unit)}"
        number /= 1024


def counted(value, noun, language):
    forms = {
        'ru': {'week': ('неделя', 'недели', 'недель'), 'day': ('день', 'дня', 'дней'),
               'group': ('комплект', 'комплекта', 'комплектов'),
               'file': ('файл', 'файла', 'файлов'), 'message': ('сообщение', 'сообщения', 'сообщений')},
        'de': {'week': ('Woche', 'Wochen'), 'day': ('Tag', 'Tage'), 'group': ('Paket', 'Pakete'),
               'file': ('Datei', 'Dateien'), 'message': ('Nachricht', 'Nachrichten')},
        'en': {'week': ('week', 'weeks'), 'day': ('day', 'days'), 'group': ('group', 'groups'),
               'file': ('file', 'files'), 'message': ('message', 'messages')},
    }
    options = forms[language if language in forms else 'en'][noun]
    if language == 'ru':
        index = 0 if value % 10 == 1 and value % 100 != 11 else 1 if value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14) else 2
    else:
        index = 0 if value == 1 else 1
    return f'{value} {options[index]}'


def flat_icon(kind):
    pixmap = QPixmap(72, 72)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#fff0ef' if kind in ('critical', 'warning') else '#e8f2ff'))
    painter.drawEllipse(QRectF(1, 1, 34, 34))
    painter.setPen(QColor('#ad4d4a' if kind in ('critical', 'warning') else '#176dcc'))
    painter.setFont(QFont('Arial', 21, QFont.Weight.Bold))
    painter.drawText(QRectF(0, 0, 36, 36), Qt.AlignmentFlag.AlignCenter, '?' if kind == 'question' else '!' if kind in ('critical', 'warning') else 'i')
    painter.end()
    return pixmap


def themed_message(parent, kind, title, text, buttons=QMessageBox.StandardButton.Ok, default=QMessageBox.StandardButton.NoButton):
    box = QMessageBox(parent)
    style_light_dialog(box)
    box.setWindowTitle(title)
    box.setText(title)
    box.setInformativeText(text)
    box.setIconPixmap(flat_icon(kind))
    box.setStandardButtons(buttons)
    language = getattr(parent, 'language', 'en')
    for standard, key in [(QMessageBox.StandardButton.Ok, 'OK'), (QMessageBox.StandardButton.Yes, 'Yes'), (QMessageBox.StandardButton.No, 'No')]:
        button = box.button(standard)
        if button:
            button.setText(tr(key, language))
            button.setFixedHeight(44)
            if standard in (QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Yes):
                button_role(button)
    if default != QMessageBox.StandardButton.NoButton:
        box.setDefaultButton(default)
    return box.exec()
