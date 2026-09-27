"""Folder scanning and deterministic planning for weekly study uploads.

This module deliberately has no Qt or Telegram dependencies so its rules stay
easy to review and test in isolation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path


class ItemKind(str, Enum):
    TEXT = "text"
    FILE = "file"


class UploadMode(str, Enum):
    """Source mode for one immutable queue snapshot."""

    MEDIA_GROUPS = "media_groups"
    WEEKLY_STUDY = "weekly_study"
    PUBLICATION_PLAN = "publication_plan"


class FileCategory(str, Enum):
    WEEK_MATERIALS = "week_materials"
    AUDIO_VIDEO = "audio_video"
    SUBTITLES = "subtitles"
    SCREENSHOTS = "screenshots"
    EXTRA_MATERIALS = "extra_materials"
    OTHER = "other"


@dataclass(frozen=True)
class WeeklyFile:
    key: str
    week_key: str
    day_key: str | None
    category: FileCategory
    path: Path
    relative_path: str
    name: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class WeeklyDay:
    key: str
    week_key: str
    day: date
    path: Path
    files: tuple[WeeklyFile, ...]


@dataclass(frozen=True)
class WeeklyWeek:
    key: str
    number: int
    name: str
    path: Path
    week_files: tuple[WeeklyFile, ...]
    days: tuple[WeeklyDay, ...]


@dataclass(frozen=True)
class ScanNotice:
    path: str
    message: str
    blocking: bool = False


@dataclass(frozen=True)
class WeeklyScanResult:
    root: Path
    weeks: tuple[WeeklyWeek, ...]
    notices: tuple[ScanNotice, ...] = ()
    excluded: tuple[ScanNotice, ...] = ()


@dataclass(frozen=True)
class WeeklyPlanItem:
    key: str
    kind: ItemKind
    week_key: str
    day_key: str | None
    category: FileCategory | None
    text: str | None = None
    path: Path | None = None
    relative_path: str | None = None
    name: str | None = None
    size: int = 0
    mtime_ns: int = 0
    sha256: str | None = None
    position: int = 0
    group_key: str | None = None
    operation_key: str | None = None


@dataclass(frozen=True)
class WeeklyUploadPlan:
    items: tuple[WeeklyPlanItem, ...]
    root: Path
    profile_id: str = ""
    account_id: int | None = None
    chat_id: int | str | None = None
    chat_title: str = ""
    publication_project_id: str = ""
    publication_revision: int | None = None
    mode: UploadMode = UploadMode.WEEKLY_STUDY

    @property
    def file_count(self) -> int:
        return sum(item.kind is ItemKind.FILE for item in self.items)

    @property
    def message_count(self) -> int:
        return len(self.items)

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.items if item.kind is ItemKind.FILE)


def build_media_group_plan(groups, root: Path, *, profile_id: str = "",
                           account_id: int | None = None,
                           chat_id: int | str | None = None,
                           chat_title: str = "") -> WeeklyUploadPlan:
    """Convert ordered media bundles to the shared journal plan format.

    Audio/video files remain separate send operations. SRT files retain the
    historical batches of at most ten, while each attachment keeps its own ID
    and journal row.
    """
    root = Path(root).expanduser().resolve()
    items: list[WeeklyPlanItem] = []
    for group in groups:
        ordered_files = [*group.media, *group.russian, *group.german]
        if not ordered_files:
            continue
        group_key = f"bundle:{Path(ordered_files[0]).resolve().relative_to(root).as_posix()}"
        media_files = list(group.media)
        subtitle_files = [*group.russian, *group.german]

        def add(path: Path, category: FileCategory, operation_key: str):
            path = Path(path).resolve(strict=True)
            relative = path.relative_to(root).as_posix()
            info = path.stat()
            key = f"file:{relative}"
            items.append(WeeklyPlanItem(
                key=key, kind=ItemKind.FILE, week_key=f"group:{group.name}", day_key=None,
                category=category, path=path, relative_path=relative,
                name=path.name, size=info.st_size, mtime_ns=info.st_mtime_ns,
                position=len(items) + 1, group_key=group_key,
                operation_key=operation_key,
            ))

        for index, path in enumerate(media_files):
            add(path, FileCategory.AUDIO_VIDEO, f"{group_key}:media:{index}")
        for start in range(0, len(subtitle_files), 10):
            operation_key = f"{group_key}:subtitles:{start // 10}"
            for path in subtitle_files[start:start + 10]:
                add(path, FileCategory.SUBTITLES, operation_key)

    return WeeklyUploadPlan(tuple(items), root, profile_id, account_id,
                            chat_id, chat_title, mode=UploadMode.MEDIA_GROUPS)


_WEEK = re.compile(r"^Неделя[\s_]+(\d+)(?:\b|[_\s-])", re.IGNORECASE)
_AUDIO_VIDEO = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac",
                ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi"}
_CATEGORY_DIRS = {
    "01_аудио": FileCategory.AUDIO_VIDEO,
    "02_субтитры": FileCategory.SUBTITLES,
}
_FIXED_FILES = {
    "03_скриншоты.zip": FileCategory.SCREENSHOTS,
    "04_дополнительные_материалы.zip": FileCategory.EXTRA_MATERIALS,
}


def _natural_key(value: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part.casefold()
                 for part in re.split(r"(\d+)", unicodedata.normalize("NFC", value)))


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _ignored_system(path: Path) -> bool:
    parts = path.parts
    return "__MACOSX" in parts or path.name == ".DS_Store" or path.name.startswith("._")


def _files_below(root: Path, folder: Path, notices: list[ScanNotice], excluded: list[ScanNotice]):
    """Walk without following symlinks; surface hidden and linked paths."""
    result: list[Path] = []
    stack = [folder]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: (_natural_key(p.name), _relative(root, p)))
        except OSError as exc:
            notices.append(ScanNotice(_relative(root, current), f"Не удалось прочитать папку: {exc}", True))
            continue
        for entry in entries:
            rel = _relative(root, entry)
            if _ignored_system(entry):
                continue
            if entry.is_symlink():
                notices.append(ScanNotice(rel, "Символическая ссылка не обходится."))
                continue
            if entry.name.startswith("."):
                excluded.append(ScanNotice(rel, "Скрытый файл или папка исключены."))
                continue
            try:
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    result.append(entry)
            except OSError as exc:
                notices.append(ScanNotice(rel, f"Не удалось проверить путь: {exc}", True))
    return sorted(result, key=lambda p: (_natural_key(p.name), _relative(root, p)))


def scan_weekly_folder(root: Path) -> WeeklyScanResult:
    """Scan a week/day folder tree and report malformed entries, never guess dates."""
    root = Path(root).expanduser().resolve()
    notices: list[ScanNotice] = []
    excluded: list[ScanNotice] = []
    if not root.exists() or not root.is_dir():
        return WeeklyScanResult(root, (), (ScanNotice(str(root), "Корневая папка отсутствует или недоступна.", True),))
    weeks: list[WeeklyWeek] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (_natural_key(p.name), _relative(root, p)))
    except OSError as exc:
        return WeeklyScanResult(root, (), (ScanNotice(str(root), f"Не удалось прочитать папку: {exc}", True),))

    for entry in entries:
        rel = _relative(root, entry)
        if _ignored_system(entry):
            continue
        if entry.is_symlink():
            notices.append(ScanNotice(rel, "Символическая ссылка не обходится."))
            continue
        if entry.name.startswith("."):
            excluded.append(ScanNotice(rel, "Скрытый файл или папка исключены."))
            continue
        match = _WEEK.match(entry.name)
        if not entry.is_dir() or not match:
            notices.append(ScanNotice(rel, "Ожидается папка «Неделя <номер> …»."))
            continue

        week_key = f"week:{rel}"
        week_number = int(match.group(1))
        week_files: list[WeeklyFile] = []
        days: list[WeeklyDay] = []
        try:
            children = sorted(entry.iterdir(), key=lambda p: (_natural_key(p.name), _relative(root, p)))
        except OSError as exc:
            notices.append(ScanNotice(rel, f"Не удалось прочитать неделю: {exc}", True))
            continue

        day_dirs: list[tuple[date, Path]] = []
        for child in children:
            child_rel = _relative(root, child)
            if _ignored_system(child):
                continue
            if child.is_symlink():
                notices.append(ScanNotice(child_rel, "Символическая ссылка не обходится."))
                continue
            if child.name.startswith("."):
                excluded.append(ScanNotice(child_rel, "Скрытый файл или папка исключены."))
                continue
            if child.is_dir():
                try:
                    parsed = date.fromisoformat(child.name)
                    if parsed.isoformat() != child.name:
                        raise ValueError
                    day_dirs.append((parsed, child))
                except ValueError:
                    notices.append(ScanNotice(child_rel, "Папка дня должна иметь действительную дату YYYY-MM-DD."))
            elif child.is_file():
                week_files.append(_make_file(root, week_key, None, FileCategory.WEEK_MATERIALS, child))
            elif child.exists():
                notices.append(ScanNotice(child_rel, "Не удалось прочитать путь."))

        day_dirs.sort(key=lambda value: (value[0], _relative(root, value[1])))
        for parsed_day, day_path in day_dirs:
            day_key = f"day:{_relative(root, day_path)}"
            categorized: list[WeeklyFile] = []
            for path in _files_below(root, day_path, notices, excluded):
                rel_parts = Path(_relative(day_path, path)).parts
                top = rel_parts[0].casefold() if len(rel_parts) > 1 else ""
                base = path.name.casefold()
                if top in _CATEGORY_DIRS:
                    category = _CATEGORY_DIRS[top]
                    if category is FileCategory.AUDIO_VIDEO and path.suffix.casefold() not in _AUDIO_VIDEO:
                        category = FileCategory.OTHER
                    elif category is FileCategory.SUBTITLES and path.suffix.casefold() != ".srt":
                        category = FileCategory.OTHER
                elif base in _FIXED_FILES:
                    category = _FIXED_FILES[base]
                elif path.suffix.casefold() == ".srt":
                    category = FileCategory.SUBTITLES
                elif path.suffix.casefold() in _AUDIO_VIDEO:
                    category = FileCategory.AUDIO_VIDEO
                else:
                    category = FileCategory.OTHER
                categorized.append(_make_file(root, week_key, day_key, category, path))
            categorized.sort(key=lambda f: (_natural_key(f.name), f.relative_path.casefold(), f.relative_path))
            days.append(WeeklyDay(day_key, week_key, parsed_day, day_path, tuple(categorized)))

        week_files.sort(key=lambda f: (_natural_key(f.name), f.relative_path.casefold(), f.relative_path))
        weeks.append(WeeklyWeek(week_key, week_number, entry.name, entry, tuple(week_files), tuple(days)))

    weeks.sort(key=lambda w: (w.number, _natural_key(w.name), _relative(root, w.path)))
    # The week-level pass also traverses day folders to separate files. Keep
    # each diagnostic path once even when it is seen by both passes.
    unique_notices = tuple(dict.fromkeys(notices))
    unique_excluded = tuple(dict.fromkeys(excluded))
    return WeeklyScanResult(root, tuple(weeks), unique_notices, unique_excluded)


def _make_file(root: Path, week_key: str, day_key: str | None, category: FileCategory, path: Path) -> WeeklyFile:
    stat = path.stat()
    rel = _relative(root, path)
    key = f"file:{rel}"
    return WeeklyFile(key, week_key, day_key, category, path, rel, path.name, stat.st_size, stat.st_mtime_ns)


_CATEGORY_ORDER = (FileCategory.AUDIO_VIDEO, FileCategory.SUBTITLES, FileCategory.SCREENSHOTS,
                   FileCategory.EXTRA_MATERIALS, FileCategory.OTHER)
_CATEGORY_TITLE = {
    FileCategory.AUDIO_VIDEO: "Аудио и видео",
    FileCategory.SUBTITLES: "Субтитры",
    FileCategory.SCREENSHOTS: "Скриншоты",
    FileCategory.EXTRA_MATERIALS: "Дополнительные материалы",
    FileCategory.OTHER: "Прочие материалы",
}


def build_weekly_plan(scan: WeeklyScanResult, selected_week_keys: set[str] | None = None,
                      selected_day_keys: set[str] | None = None,
                      selected_week_material_keys: set[str] | None = None,
                      *, profile_id: str = "", account_id: int | None = None,
                      chat_id: int | str | None = None, chat_title: str = "") -> WeeklyUploadPlan:
    """Create stable order. Headers appear only for groups containing chosen files."""
    selected_week_keys = selected_week_keys if selected_week_keys is not None else {w.key for w in scan.weeks}
    selected_day_keys = selected_day_keys if selected_day_keys is not None else {
        d.key for w in scan.weeks for d in w.days
    }
    selected_week_material_keys = selected_week_material_keys if selected_week_material_keys is not None else {
        w.key for w in scan.weeks if w.week_files
    }
    items: list[WeeklyPlanItem] = []

    def add_text(key: str, week: WeeklyWeek, day: WeeklyDay | None, text: str):
        items.append(WeeklyPlanItem(key, ItemKind.TEXT, week.key, day.key if day else None,
                                    None, text=text, position=len(items) + 1))

    def add_file(file: WeeklyFile):
        items.append(WeeklyPlanItem(file.key, ItemKind.FILE, file.week_key, file.day_key,
                                    file.category, path=file.path, relative_path=file.relative_path,
                                    name=file.name, size=file.size, mtime_ns=file.mtime_ns,
                                    position=len(items) + 1))

    for week in scan.weeks:
        if week.key not in selected_week_keys:
            continue
        chosen_week_files = [f for f in week.week_files if week.key in selected_week_material_keys]
        chosen_days = [d for d in week.days if d.key in selected_day_keys]
        if not chosen_week_files and not any(d.files for d in chosen_days):
            continue
        add_text(f"header:{week.key}", week, None, week.name)
        for file in chosen_week_files:
            add_file(file)
        for day in chosen_days:
            groups = {category: [f for f in day.files if f.category is category] for category in _CATEGORY_ORDER}
            present = [category for category in _CATEGORY_ORDER if groups[category]]
            if not present:
                continue
            add_text(f"header:{day.key}", week, day, day.day.isoformat())
            for category in present:
                for file in groups[category]:
                    add_file(file)
    return WeeklyUploadPlan(tuple(items), scan.root, profile_id, account_id, chat_id, chat_title)


@dataclass(frozen=True)
class WeeklyProgress:
    phase: str
    current_week: str = ""
    current_day: str = ""
    current_item: str = ""
    current_bytes: int = 0
    current_total_bytes: int = 0
    total_bytes: int = 0
    completed_items: int = 0
    total_items: int = 0
    status: str = ""
    wait_seconds: int | None = None
