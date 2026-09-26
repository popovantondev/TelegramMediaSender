from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "src/telegram_media_sender/assets/app-icon.svg"
ICONSET = ROOT / "build-assets/TelegramMediaSender.iconset"
ICON = ROOT / "build-assets/TelegramMediaSender.icns"
app = QGuiApplication.instance() or QGuiApplication([])

ICONSET.mkdir(parents=True, exist_ok=True)
renderer = QSvgRenderer(str(SVG))
if not renderer.isValid():
    raise SystemExit(f"Invalid SVG icon: {SVG}")

for logical_size, name in ((16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
                           (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
                           (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
                           (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
                           (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png")):
    pixmap = QPixmap(QSize(logical_size, logical_size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    if not pixmap.save(str(ICONSET / name), "PNG"):
        raise SystemExit(f"Could not save {name}")

subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICON)], check=True)
