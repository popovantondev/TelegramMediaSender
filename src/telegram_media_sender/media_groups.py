"""Discover ordered bundles of media and/or subtitles in one folder."""
from __future__ import annotations

import unicodedata
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from .i18n import tr

MEDIA_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi",
    ".m4a", ".mp3", ".aac", ".ogg", ".wav", ".flac",
}


@dataclass
class Group:
    name: str
    media: list[Path] = field(default_factory=list)
    russian: list[Path] = field(default_factory=list)
    german: list[Path] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.media or self.russian or self.german)

    @property
    def has_extra_subtitles(self) -> bool:
        return len(self.russian) > 1 or len(self.german) > 1

    @property
    def files(self) -> list[Path]:
        return [*self.media, *self.russian, *self.german]


@dataclass(frozen=True)
class GroupIssue:
    name: str
    media: int
    russian: int
    german: int
    kind: str = "incomplete"

    def format(self, language: str) -> str:
        if self.kind == "extra_subtitles":
            return tr("Extra subtitles for {name}: all {count} matching subtitle files will be sent.",
                      language, name=self.name, count=self.russian + self.german)
        return tr("Incomplete group: {name}; media {media}, Russian .ru.srt {russian}, German .srt {german}",
                  language, name=self.name, media=self.media, russian=self.russian, german=self.german)


def _key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _group_number(name: str) -> str | None:
    match = re.match(r"^\s*(\d+)(?=\D|$)", name)
    return match.group(1) if match else None


def _sort_key(name: str) -> tuple[int, int, str]:
    number = _group_number(name)
    return (0, int(number), _key(name)) if number else (1, 0, _key(name))


def _parts(name: str) -> tuple[str | None, list[str], str]:
    normalized = unicodedata.normalize("NFKC", name).casefold().replace("ё", "е")
    number = re.match(r"^\s*(\d{3,})(?=\D|$)", normalized)
    suffix = normalized[number.end():] if number else normalized
    tokens = [re.sub(r"\d+$", "", token) for token in re.findall(r"[^\W_]+", suffix)]
    tokens = [token for token in tokens if token]
    return (number.group(1) if number else None, tokens, "".join(tokens))


def _match_score(media_name: str, subtitle_name: str) -> int:
    if _key(media_name) == _key(subtitle_name):
        return 1000
    media_number, media_tokens, media_compact = _parts(media_name)
    subtitle_number, subtitle_tokens, subtitle_compact = _parts(subtitle_name)
    if media_number and subtitle_number and media_number != subtitle_number:
        return -1
    same_number = bool(media_number and media_number == subtitle_number)
    if not media_compact or not subtitle_compact:
        return 300 if same_number else -1
    ratio = SequenceMatcher(None, media_compact, subtitle_compact).ratio()
    prefix = 0
    for left, right in zip(media_compact, subtitle_compact):
        if left != right:
            break
        prefix += 1
    shared_token = any(len(left) >= 3 and len(right) >= 3 and
                       (left == right or (min(len(left), len(right)) >= 4 and
                        (left.startswith(right) or right.startswith(left))))
                       for left in media_tokens for right in subtitle_tokens)
    if same_number and (prefix >= 4 or shared_token):
        return 500 + int(ratio * 100) + min(prefix, 40)
    if ratio >= .65 and (prefix >= 5 or shared_token):
        return 100 + int(ratio * 100) + min(prefix, 40)
    return -1


def attachment_name_key(name: str) -> str:
    """Canonicalize Telegram-safe filename changes without discarding the suffix."""
    normalized = unicodedata.normalize("NFKC", Path(name).name).casefold().replace("ё", "е")
    # TelegramArchive and Telegram clients can turn spaces/dots in language tags
    # into underscores (e.g. `name.ru.mp4` -> `name_ru.mp4`). Compare words and
    # extension as tokens so those safe-name rewrites still identify the file.
    return " ".join("".join(char if char.isalnum() else " " for char in normalized).split())


def scan_folder(folder: Path, language: str = "ru") -> tuple[list[Group], list[GroupIssue]]:
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError(tr("Select a regular folder containing files.", language))
    found: dict[str, Group] = {}
    subtitles: list[tuple[str, str, Path]] = []

    def get_group(stem: str) -> Group:
        number = _group_number(stem)
        key = f"number:{int(number)}" if number else f"name:{_key(stem)}"
        return found.setdefault(key, Group(name=stem))

    for path in sorted(folder.iterdir(), key=lambda item: _sort_key(item.name)):
        if not path.is_file() or path.is_symlink() or path.name.startswith("."):
            continue
        name = path.name
        lowered = name.casefold()
        if lowered.endswith(".ru.srt"):
            subtitles.append((name[:-7], "russian", path))
        elif lowered.endswith(".de.srt"):
            subtitles.append((name[:-7], "german", path))
        elif lowered.endswith(".srt"):
            subtitles.append((name[:-4], "german", path))
        elif path.suffix.casefold() in MEDIA_EXTENSIONS:
            stem = path.name[:-len(path.suffix)]
            if stem.casefold().endswith(".ru"):
                stem = stem[:-3]
            get_group(stem).media.append(path)

    media_groups = [group for group in found.values() if group.media]
    for stem, language_name, path in subtitles:
        if _group_number(stem):
            group = get_group(stem)
        else:
            scores = [(_match_score(group.name, stem), group) for group in media_groups]
            matching = [(score, group) for score, group in scores if score >= 0]
            if matching:
                best_score = max(score for score, _group in matching)
                best = [group for score, group in matching if score == best_score]
                group = best[0] if len(best) == 1 else get_group(stem)
            else:
                group = get_group(stem)
        getattr(group, language_name).append(path)

    complete, issues = [], []
    video_extensions = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi"}
    for group in found.values():
        if group.media:
            group.media.sort(key=lambda path: (0 if path.suffix.casefold() in video_extensions else 1,
                                               _sort_key(path.name)))
            primary = next((path for path in group.media if path.suffix.casefold() in video_extensions),
                           group.media[0])
            stem = primary.name[:-len(primary.suffix)]
            group.name = stem[:-3] if stem.casefold().endswith(".ru") else stem
    for group in sorted(found.values(), key=lambda item: _sort_key(item.name)):
        if group.complete:
            complete.append(group)
            if group.has_extra_subtitles:
                issues.append(GroupIssue(group.name, len(group.media), len(group.russian),
                                         len(group.german), "extra_subtitles"))
        else:
            issues.append(GroupIssue(group.name, len(group.media), len(group.russian), len(group.german)))
    return complete, issues
