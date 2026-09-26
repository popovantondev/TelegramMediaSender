from __future__ import annotations

import shutil
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "build-assets/licenses"
DEST.mkdir(parents=True, exist_ok=True)

packages = {
    "Telethon": "Telethon",
    "PySide6": "Qt for Python",
    "PySide6_Essentials": "Qt for Python Essentials",
    "PySide6_Addons": "Qt for Python Addons",
    "shiboken6": "Shiboken",
    "pyinstaller": "PyInstaller",
}
for package, label in packages.items():
    try:
        installed = distribution(package)
    except Exception:
        continue
    license_files = [file for file in (installed.files or [])
                     if "license" in str(file).casefold() or "copying" in str(file).casefold()]
    for index, file in enumerate(license_files, 1):
        source = installed.locate_file(file)
        if source.is_file():
            suffix = source.suffix or ".txt"
            name = f"{label.replace(' ', '-')}-{index}{suffix}"
            shutil.copyfile(source, DEST / name)

shutil.copyfile(ROOT / "licenses/LGPL-3.0.txt", DEST / "LGPL-3.0.txt")
shutil.copyfile(ROOT / "licenses/Apache-2.0.txt", DEST / "Apache-2.0.txt")
shutil.copyfile(ROOT / "licenses/Python-3.12-LICENSE.txt", DEST / "Python-3.12-LICENSE.txt")
